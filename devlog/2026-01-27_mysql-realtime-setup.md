# MySQL Realtime 설정 완료 (2026-01-27)

## 목표
상담사 계정(agent01~06)을 정적 pjsip.conf에서 MySQL Realtime으로 이관

## 완료된 작업

### 1. AWS 인프라 (Terraform)
- RDS MySQL 생성: `asterisk-realtime-db.cvu6ye6s6u9k.ap-northeast-2.rds.amazonaws.com`
- Security Group 설정: EC2 → RDS 3306 허용
- Secrets Manager에 DB 비밀번호 저장

### 2. 데이터베이스
- 스키마 적용: `sql/schema.sql`
  - ps_aors, ps_auths, ps_endpoints, ps_contacts 테이블
- 시드 데이터: `sql/seed_agents.sql`
  - agent01~06 계정 (비밀번호: Aivle12!)

### 3. EC2 설정

#### Security Group 수정
```bash
# EC2 SG에 아웃바운드 규칙 추가
- 3306 → RDS SG (MySQL 연결)
- 80 → 0.0.0.0/0 (apt 패키지 설치)
```

#### ODBC 설정
```ini
# /etc/odbc.ini
[asterisk-connector]
Driver = MariaDB Unicode
Server = asterisk-realtime-db.cvu6ye6s6u9k.ap-northeast-2.rds.amazonaws.com
Database = asterisk
Port = 3306
User = admin
Password = <from secrets manager>
```

#### Asterisk 설정

**/etc/asterisk/res_odbc.conf**
```ini
[asterisk]
enabled => yes
dsn => asterisk-connector
username => admin
password => <password>
pre-connect => yes
```

**/etc/asterisk/extconfig.conf**
```ini
[settings]
ps_endpoints => odbc,asterisk,ps_endpoints
ps_auths => odbc,asterisk,ps_auths
ps_aors => odbc,asterisk,ps_aors
ps_contacts => odbc,asterisk,ps_contacts
```

**/etc/asterisk/sorcery.conf** (핵심!)
```ini
[res_pjsip]
; Realtime first, then config file
endpoint=realtime,ps_endpoints
endpoint=config,pjsip.conf,criteria=type=endpoint
auth=realtime,ps_auths
auth=config,pjsip.conf,criteria=type=auth
aor=realtime,ps_aors
aor=config,pjsip.conf,criteria=type=aor
```

**/etc/asterisk/pjsip.conf**
```ini
; system 섹션 추가 필수!
[system]
type=system
```

**/etc/asterisk/modules.conf** (추가)
```ini
; 헤드리스 서버에서 크래시 방지
noload => chan_alsa.so
noload => chan_console.so
noload => chan_oss.so
noload => res_phoneprov.so
noload => res_config_ldap.so
noload => res_config_pgsql.so
noload => res_smdi.so
```

## 결과
```
pjsip show endpoints:
- agent01~06: Realtime에서 로드 (Unavailable - 미등록 상태)
- linphone-endpoint: pjsip.conf에서 로드 (Not in use)
```

## 트러블슈팅

### 문제 1: EC2 → RDS 연결 불가
- **원인**: EC2 SG 아웃바운드에 3306 규칙 없음
- **해결**: `aws ec2 authorize-security-group-egress` 로 규칙 추가

### 문제 2: ODBC 연결 실패 "Data source name not found"
- **원인**: odbc.ini의 Driver 이름 불일치
- **해결**: `Driver = MariaDB Unicode` (odbcinst.ini 확인)

### 문제 3: Asterisk 크래시 "munmap_chunk(): invalid pointer"
- **원인**: chan_alsa, res_phoneprov 등 헤드리스 서버 호환 문제
- **해결**: modules.conf에서 noload 설정

### 문제 4: res_pjsip 로드 실패 "Failed to initialize SIP system"
- **원인**: pjsip.conf에 [system] 섹션 누락
- **해결**: `[system]\ntype=system` 추가

### 문제 5: sorcery.conf 적용 시 크래시
- **원인**: 복잡한 sorcery.conf 설정
- **해결**: 최소 설정으로 단순화 (endpoint, auth, aor만)

## 다음 단계
1. SIP 클라이언트로 agent 계정 등록 테스트
2. 통화 테스트
3. 설정 파일들 git commit
