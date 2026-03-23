-- Увеличить длину поля под хэш пароля (scrypt от Werkzeug 3)
-- Выполнить один раз в базе tinder:
--   docker exec -i postgres17 psql -U postgres -d tinder -f -
-- или в psql: \i path/to/postgres_alter_password_hash.sql

ALTER TABLE "user" ALTER COLUMN password_hash TYPE VARCHAR(512);
