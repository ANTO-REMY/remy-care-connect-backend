-- ============================================================
-- reset_db.sql — Complete database wipe and rebuild for RemyAfya
-- Run as the postgres superuser or the remyafya DB owner:
--   psql -U postgres -d remyafya -f reset_db.sql
-- ============================================================

-- Drop all tables in dependency order (most dependent first)
DROP TABLE IF EXISTS next_of_kin          CASCADE;
DROP TABLE IF EXISTS profile_photos       CASCADE;
DROP TABLE IF EXISTS daily_checkins       CASCADE;
DROP TABLE IF EXISTS dietary_recommendations CASCADE;
DROP TABLE IF EXISTS educational_materials  CASCADE;
DROP TABLE IF EXISTS escalations           CASCADE;
DROP TABLE IF EXISTS mother_chw_assignments CASCADE;
DROP TABLE IF EXISTS appointment_schedule  CASCADE;
DROP TABLE IF EXISTS weekly_tips           CASCADE;
DROP TABLE IF EXISTS medical_record_types  CASCADE;
DROP TABLE IF EXISTS verifications         CASCADE;
DROP TABLE IF EXISTS user_sessions         CASCADE;
DROP TABLE IF EXISTS nurses                CASCADE;
DROP TABLE IF EXISTS chws                  CASCADE;
DROP TABLE IF EXISTS mothers               CASCADE;
DROP TABLE IF EXISTS users                 CASCADE;
DROP TABLE IF EXISTS wards                 CASCADE;
DROP TABLE IF EXISTS sub_counties          CASCADE;

-- Drop enums if they exist
DROP TYPE IF EXISTS verification_status  CASCADE;
DROP TYPE IF EXISTS user_roles           CASCADE;

-- ============================================================
-- Re-run all migrations in order
-- ============================================================

\echo '--- Running 000_create_database.sql ---'
\i migrations/000_create_database.sql

\echo '--- Running 001_create_users.sql ---'
\i migrations/001_create_users.sql

\echo '--- Running 002_create_mothers.sql ---'
\i migrations/002_create_mothers.sql

\echo '--- Running 002_create_appointment_schedule.sql ---'
\i migrations/002_create_appointment_schedule.sql

\echo '--- Running 003_create_medical_record_type.sql ---'
\i migrations/003_create_medical_record_type.sql

\echo '--- Running 004_create_chws_nurses.sql ---'
\i migrations/004_create_chws_nurses.sql

\echo '--- Running 004_create_educational_material.sql ---'
\i migrations/004_create_educational_material.sql

\echo '--- Running 004_create_verifications.sql ---'
\i migrations/004_create_verifications.sql

\echo '--- Running 005_create_dietary_recommendation.sql ---'
\i migrations/005_create_dietary_recommendation.sql

\echo '--- Running 005_create_mother_chw_assignments.sql ---'
\i migrations/005_create_mother_chw_assignments.sql

\echo '--- Running 006_create_escalations.sql ---'
\i migrations/006_create_escalations.sql

\echo '--- Running 007_create_daily_checkin.sql ---'
\i migrations/007_create_daily_checkin.sql

\echo '--- Running 008_create_weekly_tip.sql ---'
\i migrations/008_create_weekly_tip.sql

\echo '--- Running 009_create_next_of_kin.sql ---'
\i migrations/009_create_next_of_kin.sql

\echo '--- Running 010_alter_existing_tables.sql ---'
\i migrations/010_alter_existing_tables.sql

\echo '--- Running 011_emergency_cleanup_users_table.sql ---'
\i migrations/011_emergency_cleanup_users_table.sql

\echo '--- Running 012_create_profile_photos.sql ---'
\i migrations/012_create_profile_photos.sql

\echo '--- Running 013_make_mother_fields_required.sql ---'
\i migrations/013_make_mother_fields_required.sql

\echo '--- Running 014_create_subcounties_wards.sql ---'
\i migrations/014_create_subcounties_wards.sql

\echo '--- Running 015_add_ward_id_to_role_tables.sql ---'
\i migrations/015_add_ward_id_to_role_tables.sql

\echo '--- Running 016_add_sub_county_id_to_role_tables.sql ---'
\i migrations/016_add_sub_county_id_to_role_tables.sql

\echo '--- Running 017_create_user_sessions.sql ---'
\i migrations/017_create_user_sessions.sql

\echo '=== Database reset complete ==='
