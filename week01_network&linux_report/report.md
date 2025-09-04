# Week 1 리포트 — OSI/TCP-IP & 패킷 캡처

## 1. 요약
- 목표: OSI↔TCP/IP 매핑 이해, DNS→TCP→(TLS)→HTTP→종료까지 한 사이클을 캡처/해석.
- 결과: ARP/DNS/ICMP/HTTP/HTTPS pcap 확보, 3-way·FIN/ACK·(환경상 RST) 확인.
- 배운점: (예) 이름→숫자(DNS) 뒤에 반드시 TCP 악수가 선행되고, 로컬 HTTP는 lo에서만 보임 등.

## 2. 실험 환경
| 항목 | 값 |
|---|---|
| Host | Windows 10/11 + VirtualBox (NAT) |
| Guest | Kali Linux 2025.x |
| 인터페이스 | 기본: `eth0` (또는 `enp…`), 루프백: `lo` |
| 게스트 IP | 10.0.2.15 |
| 게이트웨이 | 10.0.2.2 |
| DNS 서버 | 8.8.8.8 |
| 도구 버전 | tcpdump X.X, Wireshark X.X |

> 네트워크 모드와 인터페이스는 결과에 직접 영향(예: NAT의 GW=10.0.2.2).

## 3. 공통 방법(재현 절차)
- 캡처 폴더: `~/week1/03_captures`
- 공통 옵션: `tcpdump -i <iface> -n -s 0 -vvv -w file.pcap '필터'`
- 트래픽은 캡처 **중**에 생성(dig/curl/ping/http.server).
- Wireshark 디스플레이 필터: `arp`, `icmp`, `dns`, `http`, `tcp.flags.syn==1`, `tcp.port==443 && tls`

## 4. 실험별 결과

### 4.1 ARP — “게이트웨이 MAC 알아내기”
- **목표**: 10.0.2.2(게이트웨이)의 MAC 확인
- **명령**:
  - 캡처: `tcpdump -i eth0 -w arp_scan.pcap arp`
  - 트리거: `ping -c 1 10.0.2.2` 또는 `arping -I eth0 -c 3 10.0.2.2`
- **증빙**: `03_captures/arp_scan.pcap` 스크린샷  
  - *보일 것*: `Who has 10.0.2.2? Tell 10.0.2.15` → `10.0.2.2 is at 52:55:0a:00:02:02`
- **해석**: ARP는 IP↔MAC 매핑. 첫 통신 전 브로드캐스트로 물어보고, 대상이 자기 MAC으로 응답.

### 4.2 DNS — “이름을 숫자 IP로”
- **목표**: example.com의 A 레코드 조회
- **명령**:
  - 캡처: `tcpdump -i eth0 -w dns_query.pcap '(udp port 53) or (tcp port 53)'`
  - 질의: `dig @8.8.8.8 example.com A`
- **증빙**: 요청/응답 쌍, `Transaction ID`, `Answers(A=93.184.216.34)`
- **해석**: 사람친화적 이름→IP로 변환. 브라우저 DoH는 53이 안 보이므로 도구는 `dig` 사용.

### 4.3 ICMP — “연결성 확인(Ping)”
- **목표**: 외부 도달성 확인
- **명령**:
  - 캡처: `tcpdump -i eth0 -w icmp_ping.pcap icmp`
  - 트래픽: `ping -c 4 8.8.8.8`
- **증빙**: request/reply 쌍, `id/seq`, `TTL`
- **해석**: 왕복 통신 OK, RTT는 응답 간 시간차로 추정 가능.

### 4.4 TCP 3-way & HTTP — “주문과 배달”
- **목표**: 3-way 후 GET/200 OK 확인
- **명령**:
  - 캡처: `tcpdump -i lo -w http_get.pcap 'tcp port 8000'`
  - 서버: `python3 -m http.server 8000` / 요청: `curl http://127.0.0.1:8000/`
- **증빙**: `SYN→SYN/ACK→ACK`, `GET /`, `200 OK`, `FIN/ACK`
- **해석**: TCP로 신뢰 연결 수립 → HTTP 요청/응답 → 정상 종료. 루프백 트래픽은 `lo`에서만 보임.

### 4.5 HTTPS/TLS — “보안 연결”
- **목표**: TLS 핸드셰이크(ClientHello/ServerHello) 관찰
- **명령**:
  - 캡처: `tcpdump -i eth0 -w https_tls_handshake.pcap 'tcp port 443'`
  - 요청: `curl -4 -I https://example.com` 및  
    `openssl s_client -connect example.com:443 -servername example.com </dev/null`
- **증빙**: 정상 환경이면 `ClientHello/SNI, ServerHello/Certificate`가 보임  
  (이번 실험에선 IPv6 경로에서 `RST,ACK`로 즉시 종료되는 현상 관찰)
- **해석**: 네트워크 정책/IPv6 경로 문제로 추정. IPv4 강제 시 정상화.

## 5. 패킷 흐름 다이어그램(수정본)
- 파일: `02_packet_flow_diagram.mmd`  
- 반영 내용: DNS → TCP 3-way → (TLS) → HTTP → FIN/ACK  
- 실제 IP/GW/DNS 값으로 업데이트

## 6. 트러블슈팅 로그
- **증상**: `Got 0` / 빈 pcap  
  **원인**: GW 변수 비어있음, 트래픽 미생성  
  **해결**: `IFACE/GW` 자동탐지, 캡처 중 `dig/ping/curl` 실행
- **증상**: HTTPS가 `RST,ACK` 연속  
  **추정**: IPv6 443 정책  
  **해결**: `curl -4`, `openssl s_client`로 재현·캡처

## 7. 배운 점 / 한계 / 다음 액션
- 배운 점(3개): 예) ARP→DNS→TCP→HTTP의 의존 관계, DoH 영향, lo 캡처 요령
- 한계(2개): 예) IPv6 443 환경 제약, 가상화 NAT의 관찰 범위
- 다음(2개): 브리지 모드 재실험, TLS 디섹션(만능은 아님·키 필요)

## 8. 참고자료
- 표: `01_osi_tcpip_table.md` (OSI↔TCP/IP 매핑)
- pcap: `03_captures/*.pcap`
- 명령 원본: 아래 부록

## 부록 A. 사용 명령 요약
```bash
# 예시: DNS
tcpdump -i eth0 -w dns_query.pcap '(udp port 53) or (tcp port 53)'
dig @8.8.8.8 example.com A
