-- Migration 014: Create sub_counties and wards tables with Nairobi seed data
-- 17 sub-counties, 85 wards (Nairobi County administrative units)

CREATE TABLE IF NOT EXISTS sub_counties (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS wards (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(128) NOT NULL,
    sub_county_id INTEGER      NOT NULL REFERENCES sub_counties(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_wards_sub_county_id ON wards(sub_county_id);

-- â”€â”€â”€ Seed: 17 Nairobi Sub-Counties â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
INSERT INTO sub_counties (name) VALUES
  ('Westlands'),          -- 1
  ('Dagoretti North'),    -- 2
  ('Dagoretti South'),    -- 3
  ('Langata'),            -- 4
  ('Kibra'),              -- 5
  ('Roysambu'),           -- 6
  ('Kasarani'),           -- 7
  ('Ruaraka'),            -- 8
  ('Embakasi South'),     -- 9
  ('Embakasi North'),     -- 10
  ('Embakasi Central'),   -- 11
  ('Embakasi East'),      -- 12
  ('Embakasi West'),      -- 13
  ('Makadara'),           -- 14
  ('Kamukunji'),          -- 15
  ('Starehe'),            -- 16
  ('Mathare')             -- 17
ON CONFLICT (name) DO NOTHING;

-- â”€â”€â”€ Seed: 85 Wards (5 per sub-county, except Embakasi West & Makadara = 4, Starehe & Mathare = 6) â”€â”€â”€

-- 1. Westlands (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Kitisuru'),
  ('Parklands/Highridge'),
  ('Karura'),
  ('Kangemi'),
  ('Mountain View')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Westlands'
ON CONFLICT DO NOTHING;

-- 2. Dagoretti North (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Kilimani'),
  ('Kawangware'),
  ('Gatina'),
  ('Kileleshwa'),
  ('Kabiro')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Dagoretti North'
ON CONFLICT DO NOTHING;

-- 3. Dagoretti South (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Mutu-ini'),
  ('Ngando'),
  ('Riruta'),
  ('Uthiru/Ruthimitu'),
  ('Waithaka')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Dagoretti South'
ON CONFLICT DO NOTHING;

-- 4. Langata (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Karen'),
  ('Nairobi West'),
  ('Mugumo-ini'),
  ('South C'),
  ('Nyayo Highrise')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Langata'
ON CONFLICT DO NOTHING;

-- 5. Kibra (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Laini Saba'),
  ('Lindi'),
  ('Makina'),
  ('Woodley/Kenyatta Golf Course'),
  ('Sarang''ombe')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Kibra'
ON CONFLICT DO NOTHING;

-- 6. Roysambu (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Githurai'),
  ('Kahawa West'),
  ('Zimmerman'),
  ('Roysambu'),
  ('Kahawa')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Roysambu'
ON CONFLICT DO NOTHING;

-- 7. Kasarani (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Clay City'),
  ('Mwiki'),
  ('Kasarani'),
  ('Njiru'),
  ('Ruai')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Kasarani'
ON CONFLICT DO NOTHING;

-- 8. Ruaraka (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Baba Dogo'),
  ('Utalii'),
  ('Mathare North'),
  ('Lucky Summer'),
  ('Korogocho')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Ruaraka'
ON CONFLICT DO NOTHING;

-- 9. Embakasi South (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Imara Daima'),
  ('Kwa Njenga'),
  ('Kware'),
  ('Pipeline'),
  ('Mombasa Road')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Embakasi South'
ON CONFLICT DO NOTHING;

-- 10. Embakasi North (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Kariobangi North'),
  ('Dandora Area I'),
  ('Dandora Area II'),
  ('Dandora Area III'),
  ('Dandora Area IV')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Embakasi North'
ON CONFLICT DO NOTHING;

-- 11. Embakasi Central (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Kayole North'),
  ('Kayole Central'),
  ('Kayole South'),
  ('Komarock'),
  ('Matopeni/Spring Valley')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Embakasi Central'
ON CONFLICT DO NOTHING;

-- 12. Embakasi East (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Upper Savanna'),
  ('Lower Savanna'),
  ('Embakasi'),
  ('Utawala'),
  ('Mihango')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Embakasi East'
ON CONFLICT DO NOTHING;

-- 13. Embakasi West (4 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Umoja I'),
  ('Umoja II'),
  ('Mowlem'),
  ('Kariobangi South')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Embakasi West'
ON CONFLICT DO NOTHING;

-- 14. Makadara (4 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Maringo/Hamza'),
  ('Viwandani'),
  ('Harambee'),
  ('Makongeni')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Makadara'
ON CONFLICT DO NOTHING;

-- 15. Kamukunji (5 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Pumwani'),
  ('Eastleigh North'),
  ('Eastleigh South'),
  ('Airbase'),
  ('California')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Kamukunji'
ON CONFLICT DO NOTHING;

-- 16. Starehe (6 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Nairobi Central'),
  ('Ngara'),
  ('Pangani'),
  ('Ziwani/Kariokor'),
  ('Landimawe'),
  ('Nairobi South')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Starehe'
ON CONFLICT DO NOTHING;

-- 17. Mathare (6 wards)
INSERT INTO wards (name, sub_county_id) SELECT t.name, sc.id FROM (VALUES
  ('Hospital'),
  ('Mabatini'),
  ('Huruma'),
  ('Ngei'),
  ('Mlango Kubwa'),
  ('Karo')
) AS t(name) CROSS JOIN sub_counties sc WHERE sc.name = 'Mathare'
ON CONFLICT DO NOTHING;
