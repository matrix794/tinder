-- Фильтры поиска: город в профиле + last_seen для «онлайн»
-- Выполнить в PostgreSQL после основной схемы.

ALTER TABLE "user" ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE student_profile ADD COLUMN IF NOT EXISTS city VARCHAR(100);
