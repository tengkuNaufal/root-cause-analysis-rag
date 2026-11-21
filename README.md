# root-cause-analysis-rag

Tugas besar Otomasi Jaringan dan SDN, topik 08: Explainable Agentic RAG for Root-Cause Analysis and Telemetry Remediation in NetDevOps.

## Struktur

| Folder | Isi |
|---|---|
| `lab/replica/` | lab replika enam router FRR (OSPF + eBGP) untuk menguji katalog fault |
| `faults/` | katalog 30 fault beserta ground truth |
| `scripts/` | cek kesehatan lab dan runner fault |
| `laptop/` | skrip PowerShell untuk menjalankan cek dan fault dari laptop lewat SSH |
| `data/` | jadwal benchmark dan hasil run |
| `docs/` | panduan |
| `host1/` | kode agen, retrieval, telemetry, graf, kontrak, dan utilitas Host 1 |
| `lab/host1/` | topologi dan konfigurasi sumber lab Host 1 |
| `data/host1/` | bukti eksperimen dan replay Host 1 |
| `docs/host1/` | panduan, progres, dan laporan Host 1 |

## Panduan

- [Katalog fault dan runner](docs/fault-harness.md)
- [Akses lab dari laptop](docs/akses-dari-laptop.md)
- [Client replay Host 2 dan hasil JSONL](docs/host2-replay.md)
- [Dokumentasi dan panduan Host 1](docs/host1/README.md)
