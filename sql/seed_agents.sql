-- =============================================================================
-- Asterisk PJSIP Realtime - Agent Seed Data
-- 상담사 계정 초기 데이터 (agent01 ~ agent06)
-- =============================================================================

USE asterisk;

-- =============================================================================
-- ps_aors - Address of Record for each agent
-- =============================================================================
INSERT INTO ps_aors (id, max_contacts, remove_existing, qualify_frequency) VALUES
('agent01', 1, 'yes', 60),
('agent02', 1, 'yes', 60),
('agent03', 1, 'yes', 60),
('agent04', 1, 'yes', 60),
('agent05', 1, 'yes', 60),
('agent06', 1, 'yes', 60);

-- =============================================================================
-- ps_auths - Authentication for each agent
--
-- NOTE: Passwords should be generated externally for production use.
-- Use scripts/generate_agent_passwords.sh to generate secure passwords
-- and replace the placeholders below.
-- =============================================================================
INSERT INTO ps_auths (id, auth_type, username, password) VALUES
('agent01', 'userpass', 'agent01', 'CHANGE_ME_agent01_dev'),
('agent02', 'userpass', 'agent02', 'CHANGE_ME_agent02_dev'),
('agent03', 'userpass', 'agent03', 'CHANGE_ME_agent03_dev'),
('agent04', 'userpass', 'agent04', 'CHANGE_ME_agent04_dev'),
('agent05', 'userpass', 'agent05', 'CHANGE_ME_agent05_dev'),
('agent06', 'userpass', 'agent06', 'CHANGE_ME_agent06_dev');

-- =============================================================================
-- ps_endpoints - Endpoints for each agent
-- =============================================================================
INSERT INTO ps_endpoints (
    id,
    transport,
    aors,
    auth,
    context,
    disallow,
    allow,
    direct_media,
    rtp_symmetric,
    force_rport,
    rewrite_contact,
    identify_by
) VALUES
('agent01', 'transport-udp', 'agent01', 'agent01', 'from-internal', 'all', 'ulaw,alaw', 'no', 'yes', 'yes', 'yes', 'username'),
('agent02', 'transport-udp', 'agent02', 'agent02', 'from-internal', 'all', 'ulaw,alaw', 'no', 'yes', 'yes', 'yes', 'username'),
('agent03', 'transport-udp', 'agent03', 'agent03', 'from-internal', 'all', 'ulaw,alaw', 'no', 'yes', 'yes', 'yes', 'username'),
('agent04', 'transport-udp', 'agent04', 'agent04', 'from-internal', 'all', 'ulaw,alaw', 'no', 'yes', 'yes', 'yes', 'username'),
('agent05', 'transport-udp', 'agent05', 'agent05', 'from-internal', 'all', 'ulaw,alaw', 'no', 'yes', 'yes', 'yes', 'username'),
('agent06', 'transport-udp', 'agent06', 'agent06', 'from-internal', 'all', 'ulaw,alaw', 'no', 'yes', 'yes', 'yes', 'username');

-- =============================================================================
-- Verification queries
-- =============================================================================
-- SELECT * FROM ps_aors;
-- SELECT * FROM ps_auths;
-- SELECT * FROM ps_endpoints;
