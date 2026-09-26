-- depends:

CREATE TABLE IF NOT EXISTS resume (
    resume_uuid                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_uuid                 UUID         NOT NULL,
    title                      VARCHAR(200) NOT NULL,
    descriptions               TEXT,
    previous_works             TEXT,
    powers_ids                 INT[]        NOT NULL DEFAULT '{}',
    work_experience            INT          NOT NULL DEFAULT 0,
    offer                      INT,
    invitations_corp_uuids     UUID[]       NOT NULL DEFAULT '{}',
    new_invitations_corp_uuids UUID[]       NOT NULL DEFAULT '{}',
    created_at                 TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_resume_created_at ON resume (created_at DESC);
