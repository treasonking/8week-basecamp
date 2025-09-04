# Target Setup: OWASP Juice Shop

## 실행 정보
- 실행 호스트: WIN10-01 (Host-Only IP: 10.10.10.20)
- 실행 명령:docker run --rm -p 10.10.0.15:3000:3000 bkimminich/juice-shop


## 포트 바인딩
| 호스트 IP | 포트 | 컨테이너 포트 | 프로토콜 | 비고 |
|---|---:|---:|---|---|
| 10.10.0.15 | 3000 | 3000 | TCP | Host-Only 바인딩(외부 노출 없음) |

## 버전/이미지
- `docker images bkimminich/juice-shop` [출력 첨부](https://github.com/treasonking/8week-basecamp/blob/main/week03_lab_build/screenshots/01_docker-run-juiceshop.png)
- `docker image inspect` 결과에서 **Image ID/RepoDigest** 기재 sha256:c6f965f8929c2c43676e3ac55cd19d482c0084400195db07ed7513a04f3468b5 tag: 'latest'
- 예: `sha256:xxxxxxxx`, tag: `latest` (작성일시 기준)

## 접근 확인
- Kali `nmap -sV 10.10.10.20 -p 3000` → **open** [출력 첨부](https://github.com/treasonking/8week-basecamp/blob/main/week03_lab_build/screenshots/05_kali-nmap-3000.png)
- 브라우저 `http://10.10.0.15:3000` 스크린샷 첨부  [출력 첨부](https://github.com/treasonking/8week-basecamp/blob/main/week03_lab_build/screenshots/03_browser-juiceshop.png)
