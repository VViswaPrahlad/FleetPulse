"""Execute a named, checked-in local Gold SQL demonstration query."""
import argparse
import json
from src.analytics.build_gold import ROOT, OUTPUT, TABLES, connect, literal

QUERIES = ROOT/'sql/analytics'


def execute(name):
    available = {p.stem:p for p in QUERIES.glob('*.sql')}
    if name not in available:
        raise ValueError(f'Unknown query {name!r}; available: {sorted(available)}')
    with connect() as con:
        for table in TABLES:
            path = OUTPUT/f'{table}.parquet'
            if not path.exists():
                raise FileNotFoundError('Generate Gold before running analytics queries')
            con.execute(f'CREATE VIEW {table} AS SELECT * FROM read_parquet({literal(path.as_posix())})')
        cursor = con.execute(available[name].read_text(encoding='utf-8'))
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns,row)) for row in cursor.fetchall()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query',choices=sorted(p.stem for p in QUERIES.glob('*.sql')))
    args = parser.parse_args()
    print(json.dumps(execute(args.query),indent=2,default=str))


if __name__=='__main__':
    main()
