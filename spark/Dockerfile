FROM apache/spark:3.5.0

COPY target/scala-2.12/rag-preprocessing-assembly-0.1.jar /opt/spark/jars/

ENV SPARK_EXTRA_CLASSPATH=/opt/spark/jars/*
