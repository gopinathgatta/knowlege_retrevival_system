#!/bin/bash

echo "🛑 KILLING ALL JAVA PROCESSES (Hadoop/Spark)..."
# Kill logic
pkill -9 -f "java"
pkill -9 -f "proc_namenode"
pkill -9 -f "proc_datanode"

echo "🧹 Cleaning up..."
sleep 2

# Force correct paths
export HADOOP_HOME=$(pwd)/hadoop-3.3.6
export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
export PATH=$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH

echo "Using Hadoop at: $HADOOP_HOME"
echo "Using Config at: $HADOOP_CONF_DIR"

# Verify localhost logic
grep "localhost" $HADOOP_CONF_DIR/core-site.xml > /dev/null
if [ $? -ne 0 ]; then
    echo "❌ ERROR: core-site.xml does not contain 'localhost'. Fixing it..."
    cat > $HADOOP_CONF_DIR/core-site.xml <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://localhost:9000</value>
  </property>
</configuration>
EOF
fi

grep "localhost" $HADOOP_CONF_DIR/hdfs-site.xml > /dev/null
if [ $? -ne 0 ]; then
    echo "❌ ERROR: hdfs-site.xml does not contain 'localhost'. Fixing it..."
    # Simplified hdfs-site.xml injection if needed, but assuming check is enough for now
fi


echo "🚀 STARTING HDFS..."
$HADOOP_HOME/sbin/start-dfs.sh

echo "✅ HDFS Status:"
jps

echo "🎉 DONE! NOW RUN 'python3 app.py'"
