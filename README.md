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

## Panduan

- [Katalog fault dan runner](docs/fault-harness.md)
- [Akses lab dari laptop](docs/akses-dari-laptop.md)
