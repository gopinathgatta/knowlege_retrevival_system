import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

object Preprocessing {

  def main(args: Array[String]): Unit = {

    val spark = SparkSession.builder()
      .appName("HDFS Preprocessing")
      .master("local[*]")
      .config("spark.hadoop.fs.defaultFS", "hdfs://localhost:9000")
      .getOrCreate()

    // 🔹 HDFS paths (unchanged logic, safer handling)
    val inputPath  = "hdfs://localhost:9000/rag/uploads"
    val outputPath = "hdfs://localhost:9000/rag/processed"

    // 🔹 Read raw text files from HDFS
    val rawDF = spark.read.text(inputPath)

    // 🔹 Preprocessing steps (UNCHANGED)
    val processedDF = rawDF
      .withColumn(
        "clean_text",
        lower(
          regexp_replace(col("value"), "[^a-zA-Z0-9\\s]", "")
        )
      )
      .withColumn("clean_text", regexp_replace(col("clean_text"), "\\s+", " "))
      .filter(length(col("clean_text")) > 10)

    // 🔹 Write processed output back to HDFS
    processedDF
      .select("clean_text")
      .write
      .mode("overwrite")
      .text(outputPath)

    println("✅ Preprocessing completed successfully")
    spark.stop()
  }
}
