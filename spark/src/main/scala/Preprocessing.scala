import org.apache.spark.sql.{SparkSession, DataFrame}
import org.apache.spark.sql.functions._
import org.apache.hadoop.fs.{FileSystem, Path, FSDataInputStream}
import org.apache.pdfbox.pdmodel.PDDocument
import org.apache.pdfbox.text.PDFTextStripper
import scala.collection.mutable.ArrayBuffer
import java.io.IOException

object Preprocessing {

  def main(args: Array[String]): Unit = {

    val inputPath =
      if (args.length > 0) args(0)
      else "hdfs://localhost:9000/rag/uploads"

    val processedPath =
      if (args.length > 1) args(1)
      else "hdfs://localhost:9000/rag/processed"

    // ================= SPARK SESSION =================
    val spark = SparkSession.builder()
      .appName("HDFS Preprocessing")
      .config("spark.sql.files.ignoreCorruptFiles", "true")
      .getOrCreate()

    spark.conf.set("spark.sql.shuffle.partitions", "4")

    import spark.implicits._

    val inputHdfsPath = new Path(inputPath)
    val fs = FileSystem.get(inputHdfsPath.toUri, spark.sparkContext.hadoopConfiguration)

    // ================= HELPER: PDF EXTRACTION =================
    def extractTextFromPdf(fs: FileSystem, path: Path): String = {
      var doc: PDDocument = null
      var stream: FSDataInputStream = null
      try {
        stream = fs.open(path)
        doc = PDDocument.load(stream)
        val stripper = new PDFTextStripper()
        stripper.getText(doc)
      } catch {
        case e: IOException =>
          println(s"Error reading PDF $path: ${e.getMessage}")
          ""
      } finally {
        if (doc != null) doc.close()
        if (stream != null) stream.close()
      }
    }

    // ================= UDF: LINE-AWARE CHUNKING =================
    // Lines are passed in-order. Groups them into chunks up to maxChars.
    val chunkLinesUDF = udf((lines: Seq[String], rawFileName: String) => {
      val fileName = rawFileName.split("/").last
      val chunks   = ArrayBuffer[String]()
      val buffer   = new StringBuilder()
      val maxChars = 800

      for (line <- lines) {
        val trimmed = line.trim
        if (trimmed.nonEmpty) {
          if (buffer.length + trimmed.length > maxChars && buffer.nonEmpty) {
            chunks += s"[$fileName] ${buffer.toString().trim}"
            buffer.clear()
          }
          buffer.append(trimmed).append(" ")
        }
      }
      if (buffer.nonEmpty) {
        chunks += s"[$fileName] ${buffer.toString().trim}"
      }
      chunks.toSeq
    })

    // ================= RAW LOAD =================

    if (inputPath.toLowerCase.endsWith(".pdf")) {

      // ---- PDF path ----
      println(s"PDF detected: $inputPath")
      val pdfText = extractTextFromPdf(fs, inputHdfsPath)
      val lines   = pdfText.split("\n").filter(_.trim.length > 5).toSeq

      val chunks = {
        val buf    = ArrayBuffer[String]()
        val buffer = new StringBuilder()
        for (line <- lines) {
          if (buffer.length + line.length > 800 && buffer.nonEmpty) {
            buf += s"[document.pdf] ${buffer.toString().trim}"
            buffer.clear()
          }
          buffer.append(line.trim).append(" ")
        }
        if (buffer.nonEmpty) buf += s"[document.pdf] ${buffer.toString().trim}"
        buf.toSeq
      }

      val cleanedChunks = chunks
        .map(_.replaceAll("[^\\x20-\\x7E]", " ").replaceAll("\\s+", " ").trim)
        .filter(_.length > 30)
      println(s"Total chunks (PDF): ${cleanedChunks.size}")
      spark.createDataset(cleanedChunks).toDF("chunk").repartition(4)
        .write.mode("overwrite").text(processedPath)

    } else if (fs.exists(inputHdfsPath) && fs.getFileStatus(inputHdfsPath).isDirectory) {

      // ---- Directory (Git repo) path ----
      println("Directory detected - Git repo processing")

      // ✅ BLOCKLIST approach: block known-bad extensions, allow everything else.
      // This auto-supports ALL languages (Erlang, Go, Rust, Ruby, etc.) without code changes.
      val blockedExtensions = Set(
        // Auto-generated data / config (main source of OPC-UA garbage)
        ".xml", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
        // Compiled / binary artifacts
        ".class", ".jar", ".war", ".ear", ".so", ".o", ".a", ".dll", ".exe", ".bin", ".pyc", ".pyo",
        // Media / fonts
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".webp",
        // Archives
        ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z",
        // Lock / checksum files
        ".lock", ".sum",
        // Office / PDF
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        // Minified web assets
        ".min.js", ".min.css", ".map",
        // Data files
        ".csv", ".tsv", ".parquet", ".avro", ".pb"
      )

      // Also block certain exact filenames that are always noise
      val blockedFileNames = Set(
        "package-lock.json", "yarn.lock", "Cargo.lock", "go.sum",
        "poetry.lock", "composer.lock", "Gemfile.lock"
      )

      // Skip noise/generated directories
      val skipDirs = Set(
        ".git", "target", "node_modules", "__pycache__",
        "venv", "build", "dist", "generated", "gen",
        "protobuf", "proto", "thrift", "grpc",
        "vendor", ".idea", ".vscode", "coverage", "test-results"
      )

      val files = ArrayBuffer[String]()

      def listFiles(path: Path): Unit = {
        fs.listStatus(path).foreach { status =>
          if (status.isDirectory) {
            val name = status.getPath.getName
            if (!name.startsWith(".") && !skipDirs.contains(name)) {
              listFiles(status.getPath)
            }
          } else {
            val p    = status.getPath.toString
            val name = status.getPath.getName
            val ext  = if (name.contains(".")) "." + name.split("\\.").last.toLowerCase else ""

            // Accept file if: extension NOT blocked AND filename NOT blocked AND not hidden
            if (!blockedExtensions.contains(ext) &&
                !blockedFileNames.contains(name) &&
                !name.startsWith(".")) {
              files += p
            }
          }
        }
      }

      listFiles(inputHdfsPath)
      println(s"Total valid source files detected: ${files.size}")

      if (files.nonEmpty) {
        // Use Spark-native reading (reliable, distributed)
        val baseDF = spark.read
          .text(files.toSeq: _*)
          .withColumn("file_name", input_file_name())
          // ✅ FIX: Assign a row index BEFORE any filtering to preserve line order
          .withColumn("line_idx", monotonically_increasing_id())

        // Clean WITHOUT destroying identifiers
        // Old: [^a-zA-Z0-9\s] stripped dots/underscores/colons — broke all identifiers
        // New: only remove true non-ASCII characters
        val cleanedDF = baseDF
          .withColumn("clean_line",
            regexp_replace(col("value"), "[^\\x20-\\x7E]", " "))
          .withColumn("clean_line",
            regexp_replace(col("clean_line"), "\\s+", " "))
          .withColumn("clean_line", trim(col("clean_line")))
          .filter(length(col("clean_line")) > 5)
          .select("file_name", "line_idx", "clean_line")

        // ✅ FIX: Sort by line_idx WITHIN each file before collect_list
        // Without this, collect_list returns lines in random order (scrambled README/docs)
        val groupedDF = cleanedDF
          .sort("file_name", "line_idx")    // sort globally first
          .groupBy("file_name")
          .agg(collect_list("clean_line").as("lines"))  // now order is preserved

        val chunkedDF = groupedDF
          .withColumn("chunks", chunkLinesUDF(col("lines"), col("file_name")))
          .select(explode(col("chunks")).as("chunk"))
          .filter(length(col("chunk")) > 30)
          .repartition(4)

        val count = chunkedDF.count()
        println(s"Total chunks created: $count")

        chunkedDF
          .write
          .mode("overwrite")
          .text(processedPath)

        println("Chunks written to HDFS successfully")

      } else {
        println("No valid source/doc files found")
      }

    } else {

      // ---- Single text file path ----
      println("Text file detected")
      if (fs.exists(inputHdfsPath)) {
        val baseDF = spark.read
          .text(inputPath)
          .withColumn("file_name", input_file_name())
          .withColumn("line_idx", monotonically_increasing_id())

        val cleanedDF = baseDF
          .withColumn("clean_line", regexp_replace(col("value"), "[^\\x20-\\x7E]", " "))
          .withColumn("clean_line", regexp_replace(col("clean_line"), "\\s+", " "))
          .withColumn("clean_line", trim(col("clean_line")))
          .filter(length(col("clean_line")) > 5)
          .select("file_name", "line_idx", "clean_line")

        val groupedDF = cleanedDF
          .sort("file_name", "line_idx")
          .groupBy("file_name")
          .agg(collect_list("clean_line").as("lines"))

        val chunkedDF = groupedDF
          .withColumn("chunks", chunkLinesUDF(col("lines"), col("file_name")))
          .select(explode(col("chunks")).as("chunk"))
          .filter(length(col("chunk")) > 30)
          .repartition(4)

        println(s"Total chunks: ${chunkedDF.count()}")
        chunkedDF.write.mode("overwrite").text(processedPath)
        println("Chunks written to HDFS successfully")
      }
    }

    spark.stop()
  }
}