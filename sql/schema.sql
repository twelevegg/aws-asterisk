-- =============================================================================
-- Asterisk PJSIP Realtime Tables
-- Compatible with Asterisk 20.x
-- =============================================================================

USE asterisk;

-- =============================================================================
-- ps_aors - Address of Record
-- =============================================================================
CREATE TABLE IF NOT EXISTS ps_aors (
    id VARCHAR(40) NOT NULL PRIMARY KEY,
    max_contacts INT DEFAULT 1,
    remove_existing VARCHAR(3) DEFAULT 'yes',
    minimum_expiration INT DEFAULT 60,
    maximum_expiration INT DEFAULT 3600,
    default_expiration INT DEFAULT 3600,
    qualify_frequency INT DEFAULT 60,
    qualify_timeout DECIMAL(5,2) DEFAULT 3.0,
    authenticate_qualify VARCHAR(3) DEFAULT 'no',
    outbound_proxy VARCHAR(256),
    support_path VARCHAR(3) DEFAULT 'no',
    contact VARCHAR(256),
    mailboxes VARCHAR(256),
    voicemail_extension VARCHAR(40)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- ps_auths - Authentication
-- =============================================================================
CREATE TABLE IF NOT EXISTS ps_auths (
    id VARCHAR(40) NOT NULL PRIMARY KEY,
    auth_type VARCHAR(20) DEFAULT 'userpass',
    username VARCHAR(40),
    password VARCHAR(256),
    md5_cred VARCHAR(256),
    realm VARCHAR(256),
    nonce_lifetime INT DEFAULT 32,
    refresh_token VARCHAR(256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- ps_endpoints - Endpoints
-- =============================================================================
CREATE TABLE IF NOT EXISTS ps_endpoints (
    id VARCHAR(40) NOT NULL PRIMARY KEY,
    transport VARCHAR(40),
    aors VARCHAR(200),
    auth VARCHAR(40),
    context VARCHAR(40) DEFAULT 'from-internal',
    disallow VARCHAR(200) DEFAULT 'all',
    allow VARCHAR(200) DEFAULT 'ulaw,alaw',
    direct_media VARCHAR(3) DEFAULT 'no',
    connected_line_method VARCHAR(20),
    direct_media_method VARCHAR(20),
    direct_media_glare_mitigation VARCHAR(20),
    disable_direct_media_on_nat VARCHAR(3) DEFAULT 'yes',
    dtmf_mode VARCHAR(20) DEFAULT 'rfc4733',
    external_media_address VARCHAR(256),
    force_rport VARCHAR(3) DEFAULT 'yes',
    ice_support VARCHAR(3) DEFAULT 'no',
    identify_by VARCHAR(80) DEFAULT 'username',
    mailboxes VARCHAR(256),
    moh_suggest VARCHAR(40),
    outbound_auth VARCHAR(40),
    outbound_proxy VARCHAR(256),
    rewrite_contact VARCHAR(3) DEFAULT 'yes',
    rtp_ipv6 VARCHAR(3) DEFAULT 'no',
    rtp_symmetric VARCHAR(3) DEFAULT 'yes',
    send_diversion VARCHAR(3),
    send_pai VARCHAR(3),
    send_rpid VARCHAR(3),
    timers_min_se INT DEFAULT 90,
    timers VARCHAR(20) DEFAULT 'yes',
    timers_sess_expires INT DEFAULT 1800,
    callerid VARCHAR(256),
    callerid_privacy VARCHAR(20),
    callerid_tag VARCHAR(40),
    100rel VARCHAR(20),
    aggregate_mwi VARCHAR(3),
    trust_id_inbound VARCHAR(3),
    trust_id_outbound VARCHAR(3),
    use_ptime VARCHAR(3),
    use_avpf VARCHAR(3),
    force_avp VARCHAR(3),
    media_encryption VARCHAR(20),
    inband_progress VARCHAR(3),
    call_group VARCHAR(40),
    pickup_group VARCHAR(40),
    named_call_group VARCHAR(256),
    named_pickup_group VARCHAR(256),
    device_state_busy_at INT,
    fax_detect VARCHAR(3),
    t38_udptl VARCHAR(3),
    t38_udptl_ec VARCHAR(20),
    t38_udptl_maxdatagram INT,
    t38_udptl_nat VARCHAR(3),
    t38_udptl_ipv6 VARCHAR(3),
    tone_zone VARCHAR(40),
    language VARCHAR(40) DEFAULT 'ko',
    one_touch_recording VARCHAR(3),
    record_on_feature VARCHAR(40),
    record_off_feature VARCHAR(40),
    rtp_engine VARCHAR(40),
    allow_transfer VARCHAR(3) DEFAULT 'yes',
    allow_subscribe VARCHAR(3),
    sdp_owner VARCHAR(40),
    sdp_session VARCHAR(40),
    tos_audio VARCHAR(20),
    tos_video VARCHAR(20),
    sub_min_expiry INT,
    from_domain VARCHAR(256),
    from_user VARCHAR(40),
    mwi_from_user VARCHAR(40),
    cos_audio INT,
    cos_video INT,
    message_context VARCHAR(40),
    accountcode VARCHAR(80),
    user_eq_phone VARCHAR(3),
    moh_passthrough VARCHAR(3),
    media_address VARCHAR(256),
    bind_rtp_to_media_address VARCHAR(3),
    voicemail_extension VARCHAR(40),
    incoming_mwi_mailbox VARCHAR(256),
    bundle VARCHAR(3),
    max_audio_streams INT,
    max_video_streams INT,
    webrtc VARCHAR(3),
    incoming_call_offer_pref VARCHAR(80),
    outgoing_call_offer_pref VARCHAR(80),
    stir_shaken VARCHAR(3),
    send_history_info VARCHAR(3),
    allow_unauthenticated_options VARCHAR(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- Indexes for performance
-- =============================================================================
CREATE INDEX idx_ps_aors_id ON ps_aors(id);
CREATE INDEX idx_ps_auths_id ON ps_auths(id);
CREATE INDEX idx_ps_auths_username ON ps_auths(username);
CREATE INDEX idx_ps_endpoints_id ON ps_endpoints(id);

-- =============================================================================
-- Optional: ps_contacts - Dynamic contacts (auto-populated by Asterisk)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ps_contacts (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    uri VARCHAR(255),
    expiration_time BIGINT,
    qualify_frequency INT,
    outbound_proxy VARCHAR(256),
    path VARCHAR(256),
    user_agent VARCHAR(255),
    qualify_timeout DECIMAL(5,2),
    reg_server VARCHAR(256),
    authenticate_qualify VARCHAR(3),
    via_addr VARCHAR(40),
    via_port INT,
    call_id VARCHAR(255),
    endpoint VARCHAR(40),
    prune_on_boot VARCHAR(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- Agent Status Table (상담사 상태 추적)
-- =============================================================================
CREATE TABLE IF NOT EXISTS agent_status (
    agent_id VARCHAR(40) PRIMARY KEY,
    status ENUM('available', 'busy', 'offline', 'break') DEFAULT 'offline',
    current_call_id VARCHAR(64) DEFAULT NULL,
    last_state_change TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    total_calls_today INT DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES ps_endpoints(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 상담사 초기 상태 삽입 (agent01 ~ agent06)
INSERT INTO agent_status (agent_id, status) VALUES
    ('agent01', 'available'),
    ('agent02', 'available'),
    ('agent03', 'available'),
    ('agent04', 'available'),
    ('agent05', 'available'),
    ('agent06', 'available')
ON DUPLICATE KEY UPDATE status = VALUES(status);
