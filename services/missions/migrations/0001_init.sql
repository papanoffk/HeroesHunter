-- depends:

CREATE TABLE IF NOT EXISTS missions (
    missions_uuid         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_uuid            UUID         NOT NULL,
    title                 VARCHAR(200) NOT NULL,
    descriptions          TEXT,
    location              VARCHAR(255),
    powers_ids            INT[]        NOT NULL DEFAULT '{}',
    work_experience       INT          NOT NULL DEFAULT 0,
    offer                 INT,
    respondents_uuids     UUID[]       NOT NULL DEFAULT '{}',
    new_respondents_uuids UUID[]       NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions (created_at DESC);
