-- Блокировки за мат в чатах (личка + группы). Выполнить один раз в БД tinder.

ALTER TABLE "user" ADD COLUMN IF NOT EXISTS profanity_strike_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS profanity_ban_tier INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS profanity_blocked_until TIMESTAMP NULL;
