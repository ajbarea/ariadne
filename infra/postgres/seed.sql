-- Ariadne synthetic personnel records. Fictional. No real-world entities.
-- Keyed by `alias` to match the Neo4j graph's Person.alias (H1, W4, ...) so the
-- same entity can be resolved across the relational store and the graph.

DROP TABLE IF EXISTS personnel;
CREATE TABLE personnel (
    alias           TEXT PRIMARY KEY,  -- matches Neo4j Person.alias
    name            TEXT NOT NULL,     -- matches Neo4j Person.name
    role            TEXT,
    clearance       TEXT,
    cover_employer  TEXT,              -- front company; NOT present in the graph
    last_seen_site  TEXT
);

INSERT INTO personnel (alias, name, role, clearance, cover_employer, last_seen_site) VALUES
    ('H1', 'Halberd', 'Signals Lead',     'SECRET',       'Meridian Freight Ltd',   'Compound-Alpha'),
    ('W4', 'Wren',    'Logistics Lead',   'SECRET',       'Meridian Freight Ltd',   'Compound-Alpha'),
    ('T2', 'Talon',   'Signals Analyst',  'SECRET',       'Harbor Customs Brokers', 'Compound-Beta'),
    ('O7', 'Osprey',  'Logistics Driver', 'CONFIDENTIAL', 'Delta Haulage',          'Compound-Alpha');

-- Planted cross-modality link: Halberd (H1) and Wren (W4) share the cover employer
-- 'Meridian Freight Ltd'. The graph only knows they are co-located (a 3-hop path);
-- this second, independent tie is invisible in the graph and surfaces only by
-- joining the relational store to it — the kind of non-obvious, cross-source
-- connection the harness is meant to reconcile.
