cd ~/ada_local

DATA_DIR="./default/data"

find "$DATA_DIR" -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) -print0 |
while IFS= read -r -d '' DB
do
  if ! sqlite3 "$DB" "PRAGMA schema_version;" >/dev/null 2>&1
  then
    echo "Ignoré, pas une base SQLite : $DB"
    continue
  fi

  echo "Purge de : $DB"

  {
    echo "PRAGMA foreign_keys=OFF;"
    echo "BEGIN;"

    sqlite3 "$DB" "
      SELECT 'DELETE FROM \"' || replace(name, '\"', '\"\"') || '\";'
      FROM sqlite_master
      WHERE type='table'
      AND name NOT LIKE 'sqlite_%';
    "

    sqlite3 "$DB" "
      SELECT 'DELETE FROM sqlite_sequence;'
      WHERE EXISTS (
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
        AND name='sqlite_sequence'
      );
    "

    echo "COMMIT;"
    echo "VACUUM;"
    echo "PRAGMA foreign_keys=ON;"
  } | sqlite3 "$DB"
done
