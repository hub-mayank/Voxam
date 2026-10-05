CREATE TABLE vivas (
  id TEXT PRIMARY KEY, subject TEXT, config JSONB NOT NULL, created_by TEXT, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE questions (
  id TEXT, viva_id TEXT REFERENCES vivas(id), topic TEXT, type TEXT, difficulty INT,
  text TEXT NOT NULL, key_points JSONB, source TEXT DEFAULT 'bank',
  approved_by TEXT, PRIMARY KEY (viva_id, id));
CREATE TABLE sessions (
  id UUID PRIMARY KEY, viva_id TEXT REFERENCES vivas(id), student_id TEXT NOT NULL,
  consent_at TIMESTAMPTZ NOT NULL, rules_version TEXT, started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ,
  status TEXT DEFAULT 'created', audio_uri TEXT, UNIQUE (viva_id, student_id));
CREATE TABLE turns (
  session_id UUID REFERENCES sessions(id), idx INT, role TEXT, text TEXT,
  t_start_ms INT, t_end_ms INT, phase TEXT, question_id TEXT, action TEXT, quality TEXT,
  model TEXT, prompt_version TEXT, PRIMARY KEY (session_id, idx));
CREATE TABLE scores (
  session_id UUID REFERENCES sessions(id), run INT, rubric_version TEXT, prompt_version TEXT, model TEXT,
  dims JSONB NOT NULL,
  total NUMERIC, confidence NUMERIC, low_confidence BOOLEAN, feedback JSONB,
  created_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (session_id, run));
CREATE TABLE overrides (
  id SERIAL PRIMARY KEY, session_id UUID REFERENCES sessions(id), reviewer TEXT NOT NULL,
  old_total NUMERIC, new_total NUMERIC, reason TEXT NOT NULL, at TIMESTAMPTZ DEFAULT now());
CREATE TABLE integrity_events (
  id SERIAL PRIMARY KEY, session_id UUID REFERENCES sessions(id), kind TEXT, t_ms INT, detail JSONB);
