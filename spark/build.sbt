name := "rag-preprocessing"

version := "0.1"

scalaVersion := "2.12.18"

libraryDependencies ++= Seq(
  "org.apache.spark" %% "spark-core" % "3.5.1" % "provided",
  "org.apache.spark" %% "spark-sql"  % "3.5.1" % "provided",
  "org.apache.hadoop" % "hadoop-client" % "3.3.6" % "provided",
  "org.apache.pdfbox" % "pdfbox" % "2.0.29"
)

import sbtassembly.AssemblyPlugin.autoImport._

assembly / assemblyMergeStrategy := {
  case PathList("META-INF", xs @ _*) => MergeStrategy.discard
  case PathList("javax", "xml", xs @ _*) => MergeStrategy.first
  case PathList("jakarta", "xml", xs @ _*) => MergeStrategy.first
  case PathList("org", "apache", xs @ _*) => MergeStrategy.first
  case PathList("module-info.class") => MergeStrategy.discard
  case x => MergeStrategy.first
}
