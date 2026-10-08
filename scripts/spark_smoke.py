"""Verify JVM, Python workers, and Parquet IO before downloading VED."""
import json
import sys
import tempfile
import time
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

from pyspark.sql import SparkSession


def main():
    started = time.perf_counter()
    spark = (SparkSession.builder.master("local[2]")
             .appName("FleetPulse-Day2-smoke")
             .config("spark.driver.memory", "2g")
             .config("spark.sql.shuffle.partitions", "2")
             .config("spark.sql.execution.arrow.pyspark.enabled", "true")
             .config("spark.sql.execution.arrow.pyspark.fallback.enabled", "false")
             .config("spark.python.worker.faulthandler.enabled", "true")
             .config("spark.sql.execution.pyspark.udf.faulthandler.enabled", "true")
             .config("spark.pyspark.python", sys.executable)
             .config("spark.pyspark.driver.python", sys.executable)
             .getOrCreate())
    try:
        frame = spark.createDataFrame([(1, "VED"), (2, "FleetPulse")], "id long, label string")
        assert frame.count() == 2
        with tempfile.TemporaryDirectory(prefix="spark-smoke-") as directory:
            output = str(Path(directory) / "parquet")
            Path(output).mkdir()
            pq.write_table(pa.Table.from_pandas(frame.toPandas(), preserve_index=False),
                           Path(output) / "part-00000.parquet")
            # Explicit file paths avoid Hadoop's native Windows directory listing.
            assert spark.read.parquet(str(Path(output) / "part-00000.parquet")).orderBy("id").collect() == frame.orderBy("id").collect()
        print(json.dumps({"status": "passed", "spark": spark.version,
                          "python": sys.version, "runtime_seconds": time.perf_counter() - started}))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
