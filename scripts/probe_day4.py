from pathlib import Path
import duckdb

root = Path(__file__).resolve().parents[1]
con = duckdb.connect(config={"threads": 1, "memory_limit": "2GB",
    "temp_directory": str(root / "data/tmp/duckdb-day4"),
    "autoinstall_known_extensions": False, "autoload_known_extensions": False})
print("DuckDB", duckdb.__version__)
print(con.execute("SELECT name,value FROM duckdb_settings() WHERE name IN ('allowed_directories','enable_external_access','max_temp_directory_size')").fetchall())
p = next((root / 'data/silver/ved').rglob('*.parquet'))
print(con.execute("SELECT count(*) FROM read_parquet(?)", [str(p)]).fetchall())
