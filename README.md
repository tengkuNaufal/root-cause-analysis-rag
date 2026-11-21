# root-cause-analysis-rag

Tugas besar Otomasi Jaringan dan SDN, topik 08: Explainable Agentic RAG for Root-Cause Analysis and Telemetry Remediation in NetDevOps.

## Struktur

| Folder | Isi |
|---|---|
| `lab/replica/` | lab replika enam router FRR (OSPF + eBGP) untuk menguji katalog fault |
| `faults/` | katalog 30 fault untuk lab Host 1 dan lab replika, beserta ground truth |
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

## Retrieval, linter, dan evaluator (jalur Naufal)

| Path | Isi |
|---|---|
| `rca/linter.py` | Command linter: `lint(perintah) -> {"passed", "violations"}`; CLI `python -m rca.linter file.json` |
| `rca/evaluator.py` | `python -m rca.evaluator <hasil>.jsonl` → tabel akurasi, metrik per varian, boxplot waktu |
| `rca/explain.py` | Sampling 90 penjelasan (blind, 3 penilai) dan agregasi rubrik `docs/rubrik-explainability.md` |
| `rca/retrieval/` | Eksperimen retrieval (set uji `data/retrieval_testset.yaml`, hasil `results/retrieval/`) |
| `docs/laporan/` | Kerangka laporan akhir dan draf bagian Naufal |

Linter membaca topologi langsung dari `lab/host1/frr/configs/*/frr.conf` dan katalog `faults/host1.yaml`
(ganti dengan `RCA_TOPOLOGY` / `RCA_CATALOG`). Bentuk perintah yang diterima:

```python
# bentuk kontrak agen (host1/agent_contract/models.py: ProposedCommand) — dipakai agen dan runner
{"router": "r1", "interpreter": "linux_argv",     "arguments": ["ip", "link", "set", "eth1", "mtu", "1500"]}
{"router": "r2", "interpreter": "vtysh_commands", "arguments": ["conf t", "interface eth1", "ip ospf hello-interval 1"]}
# respons agen utuh ({"proposed_patch": [...]}) dan langkah revert katalog ({"router", "steps": [...]}) juga diterima
```

`linux_argv` hanya boleh `ip link set [dev] IF mtu N|up`; perintah `ip link` di dalam `vtysh_commands` (dan
sebaliknya) ditolak dengan aturan `wrong_interpreter`. Ke-30 langkah revert `faults/host1.yaml` dipakai
sebagai test perintah benar (`tests/test_linter_host1.py`). Jalankan semua test: `pip install -r requirements.txt && pytest`.
