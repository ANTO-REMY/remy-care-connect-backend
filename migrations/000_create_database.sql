-- 000_create_database.sql
-- Creates the remyafya database if it does not exist

DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'remyafya'
   ) THEN
      PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE remyafya');
   END IF;
END
$do$;

-- Note: Requires dblink extension. If not present, run:
-- CREATE EXTENSION IF NOT EXISTS dblink;
