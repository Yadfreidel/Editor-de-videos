"""Additive, transactional migrations; an old database remains usable on failure."""
import sqlite3
from pathlib import Path

MIGRATIONS = [
    (1, 'legacy_baseline', [f'CREATE TABLE IF NOT EXISTS {t} (id TEXT PRIMARY KEY, data TEXT NOT NULL)' for t in ('projects','jobs','metrics','assets','settings')]),
    (2, 'production_workspaces', [f'CREATE TABLE IF NOT EXISTS {t} (id TEXT PRIMARY KEY, data TEXT NOT NULL)' for t in ('brand_profiles','batches','transcripts','clients','reviews','review_tokens','principals','metric_imports')]),
    (3, 'idempotent_requests', ['CREATE TABLE IF NOT EXISTS production_requests (fingerprint TEXT PRIMARY KEY, job_id TEXT NOT NULL)', 'CREATE INDEX IF NOT EXISTS migrations_name ON schema_migrations(name)']),
    (4, 'private_job_scopes', [
        """UPDATE jobs SET data=json_set(data,'$.payload.clientId',(SELECT json_extract(p.data,'$.clientId') FROM projects p WHERE p.id=json_extract(jobs.data,'$.payload.projectId'))) WHERE COALESCE(json_extract(data,'$.payload.clientId'),'')='' AND json_extract(data,'$.payload.projectId') IN (SELECT id FROM projects WHERE COALESCE(json_extract(data,'$.clientId'),'')<>'')""",
        """UPDATE jobs SET data=json_set(data,'$.payload.clientId',(SELECT json_extract(p.data,'$.clientId') FROM projects p,json_each(p.data,'$.scenes') s WHERE COALESCE(json_extract(p.data,'$.clientId'),'')<>'' AND json_extract(s.value,'$.asset')=json_extract(jobs.data,'$.payload.asset') LIMIT 1)) WHERE COALESCE(json_extract(data,'$.payload.clientId'),'')='' AND json_extract(data,'$.kind')='transcribe' AND EXISTS(SELECT 1 FROM projects p,json_each(p.data,'$.scenes') s WHERE COALESCE(json_extract(p.data,'$.clientId'),'')<>'' AND json_extract(s.value,'$.asset')=json_extract(jobs.data,'$.payload.asset'))""",
    ]),
]

def migrate(path: Path, migrations=None):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=20)
    try:
        exists=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
        applied={r[0] for r in con.execute('SELECT version FROM schema_migrations')} if exists else set()
        pending=[m for m in (MIGRATIONS if migrations is None else migrations) if m[0] not in applied]
        if pending and con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
            backup=path.with_name(path.stem+f'.before-v{pending[-1][0]}.sqlite3')
            if not backup.exists():
                with sqlite3.connect(backup) as out: con.backup(out)
        con.execute('BEGIN IMMEDIATE')
        con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        for version,name,statements in pending:
            for sql in statements: con.execute(sql)
            con.execute('INSERT INTO schema_migrations(version,name) VALUES (?,?)',(version,name))
        con.commit()
        return {'version':max([m[0] for m in (MIGRATIONS if migrations is None else migrations)],default=0),'applied':[m[1] for m in pending]}
    except Exception:
        con.rollback(); raise
    finally: con.close()
