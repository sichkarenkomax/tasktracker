#!/usr/bin/env bash
# Seeds the throwaway stack with one task carrying two comments, a participant
# and one uploaded avatar, so avatars in comments/lists can be looked at.
set -euo pipefail

BASE="http://localhost:8080/api/v1"
PASS="sup3r-secret"

j() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

# A real 64x64 PNG, assembled by hand: the upload path must receive valid image
# bytes, and a solid colour square is enough to tell a picture from a letter.
python3 - <<'PY'
import pathlib, struct, zlib

def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

width = height = 64
# RGB rows, each prefixed by the filter byte 0; a warm red so it reads at 24px.
row = b"\x00" + b"\xd9\x4f\x2e" * width
png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(row * height))
    + chunk(b"IEND", b"")
)
pathlib.Path("/tmp/seed-avatar.png").write_bytes(png)
PY

owner=$(curl -s -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"owner-seed@example.com\",\"username\":\"owner_seed\",\"password\":\"$PASS\",\"first_name\":\"Ольга\",\"last_name\":\"Организатор\"}")
otok=$(echo "$owner" | j "d['access_token']")
echo "owner registered"

viewer=$(curl -s -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"viewer-seed@example.com\",\"username\":\"viewer_seed\",\"password\":\"$PASS\",\"first_name\":\"Виктор\",\"last_name\":\"Наблюдатель\"}")
vtok=$(echo "$viewer" | j "d['access_token']")
vid=$(echo "$viewer" | j "d['user']['id']")
echo "member registered"

org=$(curl -s -X POST "$BASE/organizations" -H "Authorization: Bearer $otok" \
  -H 'Content-Type: application/json' -d '{"name":"Acme Seed"}')
oid=$(echo "$org" | j "d['id']")
echo "org $oid"

curl -s -o /dev/null -X POST "$BASE/organizations/$oid/members" -H "Authorization: Bearer $otok" \
  -H 'Content-Type: application/json' -d "{\"email\":\"viewer-seed@example.com\",\"role\":\"member\"}"
echo "member invited"

file=$(curl -s -X POST "$BASE/files?organization_id=$oid" -H "Authorization: Bearer $otok" \
  -F "file=@/tmp/seed-avatar.png;type=image/png")
fid=$(echo "$file" | j "d['id']")
curl -s -o /dev/null -X PATCH "$BASE/users/me" -H "Authorization: Bearer $otok" \
  -H 'Content-Type: application/json' -d "{\"avatar_file_id\":\"$fid\"}"
echo "owner avatar $fid"

project=$(curl -s -X POST "$BASE/projects" -H "Authorization: Bearer $otok" \
  -H 'Content-Type: application/json' -d "{\"organization_id\":\"$oid\",\"name\":\"Рассвет\"}")
pid=$(echo "$project" | j "d['id']")

task=$(curl -s -X POST "$BASE/projects/$pid/tasks?organization_id=$oid" -H "Authorization: Bearer $otok" \
  -H 'Content-Type: application/json' -d '{"title":"Проверка аватаров","description":"Лица в комментариях и списках."}')
tid=$(echo "$task" | j "d['id']")
echo "task $tid"

curl -s -o /dev/null -X POST "$BASE/tasks/$tid/comments?organization_id=$oid" -H "Authorization: Bearer $otok" \
  -H 'Content-Type: application/json' -d '{"content":"Со мной должна быть картинка."}'
curl -s -o /dev/null -X POST "$BASE/tasks/$tid/comments?organization_id=$oid" -H "Authorization: Bearer $vtok" \
  -H 'Content-Type: application/json' -d '{"content":"А со мной — буква, картинки у меня нет."}'
echo "comments posted"

curl -s -o /dev/null -X POST "$BASE/tasks/$tid/participants?organization_id=$oid" -H "Authorization: Bearer $otok" \
  -H 'Content-Type: application/json' -d "{\"user_id\":\"$vid\",\"role\":\"co_assignee\"}"
echo "participant attached"

echo "SEED_OK org=$oid project=$pid task=$tid"
