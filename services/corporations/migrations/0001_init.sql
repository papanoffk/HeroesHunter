-- depends:

CREATE TABLE IF NOT EXISTS corp (
    client_uuid UUID         PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    image       BYTEA,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_corp_name ON corp (name);
