#!/usr/bin/env bash
# Finish staging DB ownership after clone_dev_to_staging_db.sh failed on PG16
# identity sequences ("cannot change owner of sequence … Sequence is linked to table").
#
# Safe to re-run. Does NOT dump/restore (data already restored).
#
# On the VPS:
#   export STAGING_DB_PASSWORD='…'   # nexus_et_admin plaintext (optional if .env already OK)
#   sudo -E bash /var/www/nexus/backend/deploy/fix_staging_ownership.sh
#
# Or scp then:
#   sudo -E bash /tmp/fix_staging_ownership.sh
#
# Optional: STAGING_DB STAGING_USER DEV_DB ENV_FILE BACKEND SKIP_ENV SKIP_RESTART

set -euo pipefail

STAGING_DB="${STAGING_DB:-nexus_edutrust}"
STAGING_USER="${STAGING_USER:-nexus_et_admin}"
DEV_DB="${DEV_DB:-nexus_edutrust_dev}"
ENV_FILE="${ENV_FILE:-/var/www/nexus/backend/.env}"
BACKEND="${NEXUS_BACKEND:-/var/www/nexus/backend}"
SKIP_ENV="${SKIP_ENV:-0}"
SKIP_RESTART="${SKIP_RESTART:-0}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (sudo -E bash $0)" >&2
  exit 1
fi

urlencode() {
  python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

echo "==> 1/5 Re-apply ownership/grants on ${STAGING_DB} → ${STAGING_USER}"
# PG16+: own tables first (identity sequences transfer with table owner).
# Do not ALTER SEQUENCE OWNER on identity-linked sequences.
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${STAGING_DB}" <<SQL
ALTER DATABASE ${STAGING_DB} OWNER TO ${STAGING_USER};
ALTER SCHEMA public OWNER TO ${STAGING_USER};
GRANT ALL ON SCHEMA public TO ${STAGING_USER};
GRANT CREATE ON SCHEMA public TO ${STAGING_USER};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${STAGING_USER};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${STAGING_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${STAGING_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${STAGING_USER};

DO \$\$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT format('%I.%I', n.nspname, c.relname) AS fq
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r' AND n.nspname = 'public'
  LOOP
    EXECUTE format('ALTER TABLE %s OWNER TO %I', r.fq, '${STAGING_USER}');
  END LOOP;

  FOR r IN
    SELECT format('%I.%I', n.nspname, c.relname) AS fq, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('v', 'm') AND n.nspname = 'public'
  LOOP
    IF r.relkind = 'm' THEN
      EXECUTE format('ALTER MATERIALIZED VIEW %s OWNER TO %I', r.fq, '${STAGING_USER}');
    ELSE
      EXECUTE format('ALTER VIEW %s OWNER TO %I', r.fq, '${STAGING_USER}');
    END IF;
  END LOOP;

  FOR r IN
    SELECT c.relname AS seq, n.nspname AS nsp
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'S'
      AND n.nspname = 'public'
      AND c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = '${STAGING_USER}')
      AND NOT EXISTS (
        SELECT 1
        FROM pg_depend d
        JOIN pg_class t ON t.oid = d.refobjid
        WHERE d.objid = c.oid
          AND d.deptype = 'i'
          AND t.relkind = 'r'
      )
  LOOP
    EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO %I', r.nsp, r.seq, '${STAGING_USER}');
  END LOOP;
END
\$\$;
SQL

echo "==> 2/5 Realign id sequences"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${STAGING_DB}" <<'SQL'
DO $$
DECLARE r RECORD; m bigint; seq text; has_rows boolean;
BEGIN
  FOR r IN
    SELECT c.table_name
    FROM information_schema.columns c
    WHERE c.table_schema = 'public' AND c.column_name = 'id'
      AND c.data_type IN ('integer', 'bigint', 'smallint')
  LOOP
    seq := pg_get_serial_sequence(format('%I.%I', 'public', r.table_name), 'id');
    IF seq IS NULL THEN
      CONTINUE;
    END IF;
    EXECUTE format('SELECT COALESCE(MAX(id), 1) FROM %I', r.table_name) INTO m;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I)', r.table_name) INTO has_rows;
    -- Use PERFORM so boolean is not format()-interpolated as bare t/f
    PERFORM setval(seq::regclass, m, has_rows);
  END LOOP;
END
$$;
SQL

echo "==> 3/5 Verify ownership + row counts vs ${DEV_DB}"
OWN_BAD=$(sudo -u postgres psql -d "${STAGING_DB}" -tAc "
SELECT COUNT(*) FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles r ON r.oid = c.relowner
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'v', 'm', 'S')
  AND r.rolname <> '${STAGING_USER}';
")
echo "  public objects not owned by ${STAGING_USER}: ${OWN_BAD}"

DEV_TABLES=$(sudo -u postgres psql -d "${DEV_DB}" -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
STG_TABLES=$(sudo -u postgres psql -d "${STAGING_DB}" -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
DEV_ALEM=$(sudo -u postgres psql -d "${DEV_DB}" -tAc "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null || echo "(none)")
STG_ALEM=$(sudo -u postgres psql -d "${STAGING_DB}" -tAc "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null || echo "(none)")
echo "  ${DEV_DB}: tables=${DEV_TABLES} alembic=${DEV_ALEM}"
echo "  ${STAGING_DB}: tables=${STG_TABLES} alembic=${STG_ALEM}"

KEY_TABLES=(institutions programs users leads)
for t in "${KEY_TABLES[@]}"; do
  d=$(sudo -u postgres psql -d "${DEV_DB}" -tAc "SELECT COUNT(*) FROM ${t}" 2>/dev/null || echo "missing")
  s=$(sudo -u postgres psql -d "${STAGING_DB}" -tAc "SELECT COUNT(*) FROM ${t}" 2>/dev/null || echo "missing")
  if [[ "${d}" == "${s}" ]]; then
    echo "  count ${t}: OK dev=${d} staging=${s}"
  else
    echo "  count ${t}: MISMATCH dev=${d} staging=${s}" >&2
  fi
done

if [[ "${OWN_BAD}" != "0" ]]; then
  echo "WARNING: some public objects still not owned by ${STAGING_USER}" >&2
  sudo -u postgres psql -d "${STAGING_DB}" -c "
SELECT c.relkind, n.nspname||'.'||c.relname AS obj, r.rolname AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles r ON r.oid = c.relowner
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'v', 'm', 'S')
  AND r.rolname <> '${STAGING_USER}'
ORDER BY 1, 2
LIMIT 40;
" || true
fi

echo "==> 4/5 DATABASE_URL + alembic current"
if [[ "${SKIP_ENV}" != "1" ]]; then
  if [[ -z "${STAGING_DB_PASSWORD:-}" ]]; then
    # Try to keep existing .env if password not provided
    if grep -qE '^[ \t]*DATABASE_URL=' "${ENV_FILE}" 2>/dev/null; then
      echo "  STAGING_DB_PASSWORD unset — leaving ${ENV_FILE} DATABASE_URL unchanged"
    else
      echo "ERROR: set STAGING_DB_PASSWORD to update ${ENV_FILE}" >&2
      exit 1
    fi
  else
    STAGING_PW_ENC="$(urlencode "${STAGING_DB_PASSWORD}")"
    STAGING_URL="postgresql+psycopg://${STAGING_USER}:${STAGING_PW_ENC}@127.0.0.1:5432/${STAGING_DB}"
    if [[ ! -f "${ENV_FILE}" ]]; then
      echo "ERROR: ${ENV_FILE} missing" >&2
      exit 1
    fi
    cp -a "${ENV_FILE}" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
    python3 - "${ENV_FILE}" "${STAGING_URL}" <<'PY'
import re, sys
path, url = sys.argv[1], sys.argv[2]
text = open(path, "rb").read().decode("utf-8", errors="replace")
text = text.replace("\r\n", "\n").replace("\r", "\n")
new_line = f'DATABASE_URL="{url}"'
parts = text.split("\n")
out = []
replaced = False
for p in parts:
    if re.match(r"^[ \t]*DATABASE_URL\s*=", p):
        if not replaced:
            out.append(new_line)
            replaced = True
        else:
            out.append("# " + p.lstrip("#").lstrip())
    else:
        out.append(p)
if not replaced:
    out.append(new_line)
text = "\n".join(out)
if not text.endswith("\n"):
    text += "\n"
open(path, "w", encoding="utf-8", newline="\n").write(text)
redacted = re.sub(r"://([^:/]+):([^@]+)@", r"://\1:***@", url)
print("DATABASE_URL updated (password redacted):", redacted)
PY
    sed -i 's/\r$//' "${ENV_FILE}"
    chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true
    chmod 640 "${ENV_FILE}"
  fi

  # Smoke connect as app user when password available
  if [[ -n "${STAGING_DB_PASSWORD:-}" ]]; then
    export PGPASSWORD="${STAGING_DB_PASSWORD}"
    psql "postgresql://${STAGING_USER}@127.0.0.1:5432/${STAGING_DB}" -c "SELECT current_database(), current_user;" >/dev/null
    unset PGPASSWORD
    echo "  ${STAGING_USER} connect OK"
  fi
fi

# alembic current (uses app .env)
if [[ -d "${BACKEND}/.venv" ]]; then
  # shellcheck disable=SC1091
  source "${BACKEND}/.venv/bin/activate"
  cd "${BACKEND}"
  echo "  alembic current:"
  alembic current || true
  python scripts/ensure_id_sequences.py || true
else
  echo "  (no ${BACKEND}/.venv — skip alembic CLI; DB alembic_version=${STG_ALEM})"
fi

echo "==> 5/5 Restart nexus-backend"
if [[ "${SKIP_RESTART}" != "1" ]]; then
  systemctl daemon-reload || true
  systemctl restart nexus-backend
  sleep 2
  systemctl is-active nexus-backend || true
  curl -sf http://127.0.0.1:8002/ && echo " health OK" || echo "WARNING: health check failed (service may still be starting)"
else
  echo "  SKIP_RESTART=1 — not restarting"
fi

echo ""
echo "Done. Staging ownership fix complete."
echo "  tables staging=${STG_TABLES} alembic=${STG_ALEM} unowned=${OWN_BAD}"
echo "  DATABASE_URL host form: postgresql+psycopg://${STAGING_USER}:***@127.0.0.1:5432/${STAGING_DB}"
