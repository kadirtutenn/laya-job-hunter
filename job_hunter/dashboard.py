"""
Interactive Local Dashboard & Control Center for Job Hunter (Jev Jobs local-first edition).
Level 3 Autonomous Career Agent:
- Job Feed with Laya Decision metrics & match percentage bars
- Multi-Touch Outreach Sequencer: Day 0, Day 5, Day 12 draft review & 1-click approval
- Application Status & Email Inbox Watcher: Local email triage & automated status updates
- Company & Culture Intelligence: Tech debt risk, WLB signals, salary estimates, GitHub footprint
- Application preparation queue: review forms locally; never submits automatically
- Dynamic ATS PDF Resume Generator & Instant Download
"""

from __future__ import annotations

import http.server
import json
import logging
import socketserver
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from job_hunter.batch_apply import BatchApplyOrchestrator
from job_hunter.culture_intelligence import CompanyCultureAgent
from job_hunter.email_watcher import EmailInboxWatcher
from job_hunter.interview_prep import InterviewPrepAssistant
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting, ScoredJob
from job_hunter.notifier import DesktopNotifier
from job_hunter.orchestrator import JobHunterOrchestrator
from job_hunter.outreach_sequencer import OutreachSequencer
from job_hunter.pdf_generator import PDFResumeGenerator
from job_hunter.storage import LocalBrainStorage
from job_hunter.tailor import CVTailor

logger = logging.getLogger(__name__)

DEFAULT_CHROME_PROFILE_DIR = str(Path.home() / ".job_hunter" / "chrome_profile")
_hunt_logs: List[str] = []
_live_found_jobs: List[ScoredJob] = []
_hunt_cancel_event = threading.Event()

def add_hunt_log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    _hunt_logs.append(entry)
    logger.info(entry)
    if len(_hunt_logs) > 300:
        _hunt_logs.pop(0)

_hunt_state = {
    "is_running": False,
    "last_message": "Boşta",
    "discovered": 0,
    "shortlisted": 0,
}

_batch_apply_state = {
    "is_running": False,
    "progress": "",
    "applied": 0,
    "failed": 0,
}


def render_dashboard_html() -> str:
    """Renders the Level 3 single-page application dashboard."""
    return """<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ollaya Career Agent · Level 3 Autonomous Engine</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        brand: {
                            DEFAULT: '#8b5cf6',
                            hover: '#7c3aed',
                            light: '#a78bfa',
                            dark: '#6d28d9'
                        },
                        accent: '#d7ff3a'
                    }
                }
            }
        }
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; background-color: #09090b; color: #f4f4f5; }
        .score-bar-fill { transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1); }
    </style>
</head>
<body class="min-h-screen flex flex-col antialiased">
    <!-- Top Navigation -->
    <header class="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center font-bold text-white shadow-lg shadow-violet-500/20">
                    O
                </div>
                <div>
                    <span class="font-bold text-white tracking-tight">Ollaya <span class="text-violet-400">Career Agent</span></span>
                    <span class="text-xs px-2 py-0.5 ml-2 rounded-full bg-violet-950 text-violet-300 border border-violet-800 font-mono">LEVEL 3 AUTONOMOUS</span>
                </div>
            </div>

            <!-- Tabs -->
            <nav class="flex items-center gap-1 bg-zinc-900 p-1 rounded-xl border border-zinc-800 overflow-x-auto">
                <button onclick="switchTab('feed')" id="nav-feed" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-zinc-800 text-white transition whitespace-nowrap">İlan Akışı</button>
                <button onclick="switchTab('outreach')" id="nav-outreach" class="px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition whitespace-nowrap">Takip Dizisi</button>
                <button onclick="switchTab('inbox')" id="nav-inbox" class="px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition whitespace-nowrap">E-Posta Triajı</button>
                <button onclick="switchTab('batch')" id="nav-batch" class="px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition whitespace-nowrap">Toplu Başvuru</button>
                <button onclick="switchTab('hunt')" id="nav-hunt" class="px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition whitespace-nowrap">Yeni Arama</button>
                <button onclick="switchTab('profile')" id="nav-profile" class="px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-400 hover:text-white transition whitespace-nowrap">CV & Profil</button>
            </nav>

            <div class="hidden sm:flex items-center gap-3 text-xs text-zinc-400">
                <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Laya Local (:11435)</span>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        
        <!-- ================= TAB 1: JOB FEED ================= -->
        <section id="tab-feed" class="space-y-6">
            <!-- Stats Bar -->
            <div class="grid grid-cols-2 sm:grid-cols-6 gap-3">
                <div class="bg-zinc-900 border border-zinc-800 p-3.5 rounded-xl">
                    <div class="text-xs text-zinc-400 font-medium">Toplam İlan</div>
                    <div class="text-xl font-bold text-white mt-1" id="stat-total">0</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-3.5 rounded-xl">
                    <div class="text-xs text-violet-400 font-medium">Kısa Liste ⭐</div>
                    <div class="text-xl font-bold text-violet-300 mt-1" id="stat-shortlisted">0</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-3.5 rounded-xl">
                    <div class="text-xs text-emerald-400 font-medium">Mülakat 🎉</div>
                    <div class="text-xl font-bold text-emerald-300 mt-1" id="stat-interview">0</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-3.5 rounded-xl">
                    <div class="text-xs text-cyan-400 font-medium">Teknik Test 📝</div>
                    <div class="text-xl font-bold text-cyan-300 mt-1" id="stat-assessment">0</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-3.5 rounded-xl">
                    <div class="text-xs text-blue-400 font-medium">Başvuruldu 📬</div>
                    <div class="text-xl font-bold text-blue-300 mt-1" id="stat-applied">0</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 p-3.5 rounded-xl">
                    <div class="text-xs text-zinc-500 font-medium">Elenen ❌</div>
                    <div class="text-xl font-bold text-zinc-500 mt-1" id="stat-archived">0</div>
                </div>
            </div>

            <!-- Filters -->
            <div class="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/60 p-3 rounded-xl border border-zinc-800">
                <div class="flex items-center gap-2 overflow-x-auto">
                    <button onclick="setFilter('all')" class="filter-btn px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-white" data-status="all">Tümü</button>
                    <button onclick="setFilter('shortlisted')" class="filter-btn px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white" data-status="shortlisted">⭐ Kısa Liste</button>
                    <button onclick="setFilter('interview_scheduled')" class="filter-btn px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white" data-status="interview_scheduled">🎉 Mülakat</button>
                    <button onclick="setFilter('assessment')" class="filter-btn px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white" data-status="assessment">📝 Test</button>
                    <button onclick="setFilter('applied')" class="filter-btn px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white" data-status="applied">📬 Başvurulanlar</button>
                    <button onclick="setFilter('inbox')" class="filter-btn px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white" data-status="inbox">📥 Gelen Kutusu</button>
                </div>
                <div class="flex items-center gap-3">
                    <input type="text" id="search-input" placeholder="İlan veya şirket ara..." oninput="renderJobs()" class="bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-violet-500">
                </div>
            </div>

            <!-- Job Cards Grid -->
            <div id="jobs-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <!-- Dynamically populated -->
            </div>
        </section>

        <!-- ================= TAB 2: OUTREACH SEQUENCER ================= -->
        <section id="tab-outreach" class="space-y-6 hidden">
            <div class="flex items-center justify-between">
                <div>
                    <h2 class="text-lg font-bold text-white">Çok Aşamalı İletişim Dizisi (Outreach Sequence)</h2>
                    <p class="text-xs text-zinc-400">Day 0 (Başvuru), Day 5 (Takip) ve Day 12 (Değer Katma) mesaj taslaklarını inceleyin ve onaylayın.</p>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="loadOutreachSteps()" class="px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-white font-medium transition">Yenile</button>
                </div>
            </div>

            <div id="outreach-container" class="space-y-4">
                <!-- Dynamically populated -->
            </div>
        </section>

        <!-- ================= TAB 3: EMAIL INBOX TRIAGE ================= -->
        <section id="tab-inbox" class="space-y-6 hidden">
            <div class="flex items-center justify-between">
                <div>
                    <h2 class="text-lg font-bold text-white">E-Posta Gelen Kutusu ve Durum İzleyici</h2>
                    <p class="text-xs text-zinc-400">Gelen iş arama e-postaları yerel Laya modeli ile sınıflandırılır ve ilan durumları otomatik güncellenir.</p>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="simulateMockEmail()" class="px-3 py-1.5 rounded-lg text-xs bg-violet-600 hover:bg-violet-700 text-white font-medium transition">🧪 Örnek E-Posta Simüle Et</button>
                    <button onclick="loadEmailEvents()" class="px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-white font-medium transition">Yenile</button>
                </div>
            </div>

            <div id="email-events-container" class="space-y-3">
                <!-- Dynamically populated -->
            </div>
        </section>

        <!-- ================= TAB 4: BATCH APPLY ================= -->
        <section id="tab-batch" class="space-y-6 hidden">
            <div class="bg-zinc-900 border border-zinc-800 p-6 rounded-2xl max-w-3xl mx-auto space-y-5">
                <div>
                    <h2 class="text-lg font-bold text-white flex items-center gap-2">
                        <span>⚡ Başvuru Formu Hazırlama</span>
                    </h2>
                    <p class="text-xs text-zinc-400 mt-1">Form alanlarını kendi bilgisayarınızda incelemek için hazırlar; başvuruyu göndermez. CV taslağı yalnızca yerel profil bilgilerinizden üretilir.</p>
                </div>

                <div class="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-3">
                    <div class="flex justify-between items-center text-xs">
                        <span class="text-zinc-400">Kısa Listedeki Uygun İlanlar:</span>
                        <span class="font-bold text-violet-400" id="batch-shortlist-count">0 İlan Hazır</span>
                    </div>
                    <div class="flex items-center gap-4 text-xs">
                        <label class="flex items-center gap-2 text-zinc-300">
                            <input type="checkbox" id="batch-headful" checked class="rounded bg-zinc-800 border-zinc-700 text-violet-600 focus:ring-violet-500">
                            <span>Tarayıcıyı Ekranda Canlı Gör (Headful)</span>
                        </label>
                        <div class="flex items-center gap-2 text-zinc-300">
                            <span>Maksimum Başvuru:</span>
                            <input type="number" id="batch-limit" value="3" min="1" max="10" class="w-16 bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-white">
                        </div>
                    </div>
                </div>

                <button onclick="triggerBatchApply()" id="btn-batch-apply" class="w-full py-3 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl font-bold text-sm shadow-lg shadow-violet-500/20 transition">
                    Seçili ilanlarda formu hazırla (gönderim yapmaz)
                </button>

                <div id="batch-progress-box" class="hidden p-4 rounded-xl bg-violet-950/30 border border-violet-800/50 space-y-2">
                    <div class="flex items-center justify-between text-xs">
                        <span class="text-violet-300 font-medium" id="batch-progress-text">Formlar incelenmek üzere hazırlanıyor...</span>
                        <span class="animate-spin text-violet-400">⚙️</span>
                    </div>
                    <div class="w-full bg-zinc-800 rounded-full h-2">
                        <div id="batch-progress-bar" class="bg-violet-500 h-2 rounded-full" style="width: 20%"></div>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= TAB 5: HUNT LAUNCHER ================= -->
        <section id="tab-hunt" class="space-y-6 hidden">
            <div class="bg-zinc-900 border border-zinc-800 p-6 rounded-2xl max-w-2xl mx-auto space-y-4">
                <div class="flex items-center justify-between pb-2 border-b border-zinc-800">
                    <div>
                        <h2 class="text-lg font-bold text-white flex items-center gap-2">
                            <span>Otonom Tarayıcı Avı & LinkedIn Entegrasyonu</span>
                            <span id="session-status-badge" class="px-2 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400 font-mono">Kontrol ediliyor...</span>
                        </h2>
                        <p class="text-xs text-zinc-400">Laya Karar Modeli ve Playwright ile ilanları otomatik keşfedin ve puanlayın.</p>
                    </div>
                    <button onclick="triggerLogin()" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-bold text-xs shadow transition flex items-center gap-1.5">
                        <span>🔑 LinkedIn'e Giriş Yap</span>
                    </button>
                </div>

                <!-- LinkedIn Search Filters Panel -->
                <div class="bg-zinc-950 p-4 rounded-xl border border-zinc-800/80 space-y-3 text-xs">
                    <div class="font-bold text-zinc-200 flex items-center justify-between">
                        <span>🎯 LinkedIn Arama Filtreleri</span>
                        <span class="text-zinc-500 text-[10px] font-normal">Filtreleri değiştirdikçe arama URL'si otomatik senkronize olur</span>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-zinc-400 text-[11px] mb-1">Rol, şirket veya anahtar kelime</label>
                            <input type="text" id="filter-keywords" value="Python Backend" placeholder="Örn. Rollic, Backend Engineer, FastAPI" oninput="syncFiltersToUrl()" class="w-full bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-white">
                            <p class="text-[10px] text-zinc-500 mt-1">Şirket araması için şirket adını (ör. Rollic) tek başına yazabilirsiniz.</p>
                        </div>
                        <div>
                            <label class="block text-zinc-400 text-[11px] mb-1">Konum</label>
                            <input type="text" id="filter-location" value="Turkey" oninput="syncFiltersToUrl()" class="w-full bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-white">
                        </div>
                    </div>

                    <div class="grid grid-cols-4 gap-3 pt-1">
                        <div>
                            <label class="block text-zinc-400 text-[11px] mb-1">Çalışma Türü</label>
                            <div class="space-y-1 text-zinc-300">
                                <label class="flex items-center gap-1.5 cursor-pointer">
                                    <input type="checkbox" id="filter-wt-remote" checked onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600">
                                    <span>Uzaktan (Remote)</span>
                                </label>
                                <label class="flex items-center gap-1.5 cursor-pointer">
                                    <input type="checkbox" id="filter-wt-hybrid" checked onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600">
                                    <span>Hibrit (Hybrid)</span>
                                </label>
                                <label class="flex items-center gap-1.5 cursor-pointer">
                                    <input type="checkbox" id="filter-wt-onsite" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600">
                                    <span>İş Yerinde (On-site)</span>
                                </label>
                            </div>
                        </div>

                        <div>
                            <label class="block text-zinc-400 text-[11px] mb-1">Yayın Tarihi</label>
                            <select id="filter-date" onchange="syncFiltersToUrl()" class="w-full bg-zinc-900 border border-zinc-700 rounded-lg p-2 text-white">
                                <option value="all">Her Zaman</option>
                                <option value="r86400">Son 24 Saat</option>
                                <option value="r604800" selected>Son 1 Hafta</option>
                                <option value="r2592000">Son 1 Ay</option>
                            </select>
                        </div>

                        <div>
                            <label class="block text-zinc-400 text-[11px] mb-1">Deneyim Seviyesi</label>
                            <div class="space-y-1 text-zinc-300">
                                <label class="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" id="filter-exp-intern" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600"><span>Stajyer</span></label>
                                <label class="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" id="filter-exp-entry" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600"><span>Giriş seviyesi</span></label>
                                <label class="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" id="filter-exp-associate" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600"><span>Associate</span></label>
                                <label class="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" id="filter-exp-mid" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600"><span>Mid-Senior</span></label>
                                <label class="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" id="filter-exp-director" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600"><span>Director</span></label>
                                <label class="flex items-center gap-1.5 cursor-pointer"><input type="checkbox" id="filter-exp-executive" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600"><span>Executive</span></label>
                            </div>
                            <p class="text-[10px] text-zinc-500 mt-1">Boş bırakılırsa tüm seviyeler aranır.</p>
                        </div>

                        <div>
                            <label class="block text-zinc-400 text-[11px] mb-1">Özel Seçenekler</label>
                            <label class="flex items-center gap-1.5 pt-2 text-zinc-300 cursor-pointer">
                                <input type="checkbox" id="filter-easy-apply" onchange="syncFiltersToUrl()" class="rounded bg-zinc-800 border-zinc-700 text-violet-600">
                                <span class="font-medium text-emerald-400">⚡ Sadece Kolay Başvuru (Easy Apply)</span>
                            </label>
                        </div>
                    </div>
                </div>

                <!-- Final Search URL & Runner Options -->
                <div class="space-y-3 text-xs">
                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <label class="text-zinc-300 font-medium">Hedef LinkedIn Arama URL'si</label>
                            <span class="text-[10px] text-zinc-500">(İsterseniz doğrudan özel bir LinkedIn linki de yapıştırabilirsiniz)</span>
                        </div>
                        <input type="text" id="hunt-url" value="https://www.linkedin.com/jobs/search-results/?keywords=Python%20Backend" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-white font-mono text-[11px]">
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-zinc-300 font-medium mb-1">Taranacak Maksimum İlan</label>
                            <input type="number" id="hunt-max" value="5" min="1" max="25" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-white">
                        </div>
                        <div class="flex items-center gap-2 pt-5">
                            <input type="checkbox" id="hunt-headful" class="rounded bg-zinc-800 border-zinc-700 text-violet-600 focus:ring-violet-500">
                            <label for="hunt-headful" class="text-zinc-400 font-medium text-xs">Pencereyi Ekranda Göster (Headful)</label>
                        </div>
                    </div>
                    <div class="pt-2">
                        <button onclick="triggerHunt()" id="btn-hunt" class="w-full py-3 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-bold text-sm shadow-lg transition flex items-center justify-center gap-2">
                            <span>🚀 LinkedIn'de Otomatik Avı Başlat</span>
                        </button>
                        <button onclick="stopHunt()" id="btn-stop-hunt" disabled class="w-full py-2.5 bg-zinc-800 text-zinc-500 rounded-lg font-semibold text-xs transition disabled:opacity-50 enabled:bg-rose-700 enabled:text-white enabled:hover:bg-rose-600">
                            Aramayı Durdur
                        </button>
                    </div>
                </div>

                <!-- Live Agent Terminal Console -->
                <div id="hunt-console-wrapper" class="space-y-2 hidden">
                    <div class="flex items-center justify-between text-xs text-zinc-400">
                        <span class="font-bold text-white flex items-center gap-1.5">
                            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                            <span>Canlı Ajan Terminal Konsolu</span>
                        </span>
                        <span id="hunt-status-indicator" class="text-zinc-500 font-mono text-[11px]">Bağlanıyor...</span>
                    </div>
                    <div id="hunt-console" class="bg-black/95 text-emerald-400 font-mono text-[11px] p-3 rounded-xl border border-zinc-800 h-48 overflow-y-auto space-y-1 shadow-inner select-text">
                        <div class="text-zinc-600">Ajan başlatılması bekleniyor...</div>
                    </div>
                </div>

                <!-- Live Discovered Jobs Feed (Flows downward) -->
                <div id="hunt-results-wrapper" class="space-y-3 pt-2">
                    <div class="flex items-center justify-between border-b border-zinc-800 pb-2">
                        <h3 class="text-sm font-bold text-white flex items-center gap-2">
                            <span>📋 Keşfedilen İlanlar & Laya Uyum Skorları</span>
                            <span id="hunt-found-count" class="px-2 py-0.5 rounded-full text-[10px] bg-violet-950 text-violet-300 border border-violet-800 font-mono">0 İlan</span>
                        </h3>
                        <button onclick="clearAllData()" class="text-[11px] text-zinc-500 hover:text-red-400 transition flex items-center gap-1">
                            <span>🗑️ Geçmişi Temizle</span>
                        </button>
                    </div>
                    <div id="hunt-live-cards" class="space-y-3">
                        <div id="hunt-empty-placeholder" class="text-center py-8 text-xs text-zinc-500 bg-zinc-950/50 rounded-xl border border-dashed border-zinc-800">
                            Henüz arama başlatılmadı. Filtreleri belirleyip "Avı Başlat"a tıklayın; bulunan ilanlar burada anlık olarak belirecektir.
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= TAB 6: PROFILE & CV (LATEX FORMATTER & LIVE PDF VIEWER) ================= -->
        <section id="tab-profile" class="space-y-6 hidden">
            <!-- Header & Action Toolbar -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-zinc-900 border border-zinc-800 p-5 rounded-2xl shadow-xl">
                <div>
                    <div class="flex items-center gap-2">
                        <h2 class="text-lg font-bold text-white tracking-tight">Master CV & LaTeX Formatter</h2>
                        <span class="px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800 font-mono font-bold">ATS UYUMLU · TECTONIC</span>
                    </div>
                    <p class="text-xs text-zinc-400 mt-1">Teknopark & TÜBİTAK projeleriyle zenginleştirilmiş ana LaTeX şablonu ve canlı vektörel PDF önizlemesi.</p>
                </div>
                <div class="flex items-center gap-2 flex-wrap">
                    <button onclick="compileMasterTex()" id="btn-compile-tex" class="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold text-xs shadow-lg transition flex items-center gap-1.5">
                        <span>⚡ Kaydet & Tectonic ile Derle</span>
                    </button>
                    <a href="/api/profile/master-tex/download" target="_blank" class="px-3 py-2 bg-indigo-950 hover:bg-indigo-900 text-indigo-300 border border-indigo-800 rounded-lg font-medium text-xs transition flex items-center gap-1">
                        <span>📄 .tex İndir</span>
                    </a>
                    <a href="/api/profile/master-pdf?download=true" target="_blank" class="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded-lg font-medium text-xs transition flex items-center gap-1">
                        <span>📑 PDF İndir</span>
                    </a>
                    <a href="/api/profile/master-pdf" target="_blank" class="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg text-xs font-medium transition" title="Yeni sekmede tam ekran aç">
                        <span>🔍 Tam Ekran</span>
                    </a>
                </div>
            </div>

            <!-- Two-Column Grid: Left (LaTeX Editor & Profile Form) | Right (Live PDF View) -->
            <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <!-- Left Column (6 Cols): LaTeX Code Formatter & Fast Profile Meta -->
                <div class="lg:col-span-6 space-y-4 flex flex-col">
                    <!-- Collapsible Fast Profile Editor -->
                    <details class="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden group">
                        <summary class="p-3.5 text-xs font-semibold text-zinc-300 hover:text-white cursor-pointer select-none flex items-center justify-between bg-zinc-950/40">
                            <span class="flex items-center gap-2">
                                <span>👤 Aday Temel İletişim Bilgileri</span>
                                <span class="text-[10px] text-zinc-500 font-normal">(Ad, Unvan, İletişim)</span>
                            </span>
                            <span class="text-zinc-500 group-open:rotate-180 transition-transform text-xs">▼</span>
                        </summary>
                        <div class="p-4 space-y-3 text-xs border-t border-zinc-800 bg-zinc-900/60">
                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-zinc-400 font-medium mb-1">Ad Soyad</label>
                                    <input type="text" id="prof-name" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-white text-xs">
                                </div>
                                <div>
                                    <label class="block text-zinc-400 font-medium mb-1">Unvan</label>
                                    <input type="text" id="prof-title" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-white text-xs">
                                </div>
                            </div>
                            <div class="grid grid-cols-3 gap-3">
                                <div>
                                    <label class="block text-zinc-400 font-medium mb-1">E-Posta</label>
                                    <input type="text" id="prof-email" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-white text-xs">
                                </div>
                                <div>
                                    <label class="block text-zinc-400 font-medium mb-1">Telefon</label>
                                    <input type="text" id="prof-phone" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-white text-xs">
                                </div>
                                <div>
                                    <label class="block text-zinc-400 font-medium mb-1">LinkedIn URL</label>
                                    <input type="text" id="prof-linkedin" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-white text-xs">
                                </div>
                            </div>
                            <div>
                                <label class="block text-zinc-400 font-medium mb-1">Özet (Summary)</label>
                                <textarea id="prof-summary" rows="2" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-white text-xs"></textarea>
                            </div>
                            <div>
                                <label class="block text-zinc-400 font-medium mb-1">Temel Yetkinlikler (Virgülle ayırın)</label>
                                <input type="text" id="prof-skills" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-white text-xs">
                            </div>
                            <button onclick="saveProfile()" class="px-3.5 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-semibold text-xs transition">Bilgileri Güncelle</button>
                        </div>
                    </details>

                    <!-- LaTeX Editor Container -->
                    <div class="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex-1 flex flex-col space-y-3 shadow-xl">
                        <div class="flex items-center justify-between text-xs pb-1 border-b border-zinc-800">
                            <span class="font-mono text-zinc-300 font-bold flex items-center gap-1.5">
                                <span>📄</span>
                                <span>candidate/base_cv.tex</span>
                            </span>
                            <span id="tex-char-count" class="text-[11px] text-zinc-500 font-mono">0 karakter</span>
                        </div>
                        <div id="latex-compile-alert" class="hidden p-3 rounded-lg text-xs font-mono"></div>
                        <textarea id="latex-editor" rows="26" class="w-full flex-1 bg-black/95 text-emerald-400 font-mono text-xs p-4 rounded-xl border border-zinc-800 focus:border-violet-500 focus:outline-none resize-y leading-relaxed shadow-inner select-text" spellcheck="false" placeholder="LaTeX kaynak kodu yükleniyor..."></textarea>
                    </div>
                </div>

                <!-- Right Column (6 Cols): Live PDF Viewer -->
                <div class="lg:col-span-6 bg-zinc-900 border border-zinc-800 rounded-2xl p-4 flex flex-col space-y-3 shadow-xl">
                    <div class="flex items-center justify-between text-xs pb-1 border-b border-zinc-800">
                        <span class="font-bold text-white flex items-center gap-2">
                            <span>📑 Canlı Vektörel PDF Önizleme</span>
                            <span id="pdf-status-badge" class="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono">🟢 Hazır</span>
                        </span>
                        <button onclick="reloadMasterPdf()" class="text-xs text-zinc-400 hover:text-white flex items-center gap-1 transition">
                            <span>🔄 Yenile</span>
                        </button>
                    </div>
                    <div class="flex-1 w-full bg-zinc-950 rounded-xl overflow-hidden border border-zinc-800 relative min-h-[700px]">
                        <iframe id="master-cv-pdf-frame" src="/api/profile/master-pdf" class="w-full h-full min-h-[700px] rounded-xl bg-zinc-950" frameborder="0"></iframe>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- Modal: Job Detail, Tailor CV, Interview Prep & Culture -->
    <div id="modal-detail" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden flex items-center justify-center p-4">
        <div class="bg-zinc-900 border border-zinc-800 w-full max-w-4xl max-h-[90vh] rounded-2xl flex flex-col shadow-2xl overflow-hidden">
            <!-- Modal Header -->
            <div class="p-5 border-b border-zinc-800 flex items-start justify-between bg-zinc-950/50">
                <div>
                    <h3 id="modal-title" class="text-lg font-bold text-white leading-tight"></h3>
                    <div id="modal-subtitle" class="text-xs text-zinc-400 mt-1"></div>
                </div>
                <button onclick="closeModal()" class="text-zinc-400 hover:text-white p-1 rounded-lg hover:bg-zinc-800 text-lg">&times;</button>
            </div>

            <!-- Modal Sub-Tabs -->
            <div class="flex border-b border-zinc-800 bg-zinc-950/30 px-5 text-xs font-semibold gap-4">
                <button onclick="switchModalTab('desc')" id="modal-tab-desc" class="py-3 text-violet-400 border-b-2 border-violet-500">İlan Detayı</button>
                <button onclick="switchModalTab('tailor')" id="modal-tab-tailor" class="py-3 text-zinc-400 hover:text-white">CV Özelleştir & ATS PDF</button>
                <button onclick="switchModalTab('prep')" id="modal-tab-prep" class="py-3 text-zinc-400 hover:text-white">Mülakat & İletişim Kiti</button>
                <button onclick="switchModalTab('culture')" id="modal-tab-culture" class="py-3 text-zinc-400 hover:text-white">Şirket Kültür Analizi</button>
            </div>

            <!-- Modal Body -->
            <div class="p-6 overflow-y-auto flex-1 space-y-4 text-xs">
                <!-- Sub-tab 1: Description -->
                <div id="modal-content-desc" class="space-y-4">
                    <div id="modal-desc-body" class="text-zinc-300 whitespace-pre-line leading-relaxed"></div>
                </div>

                <!-- Sub-tab 2: Tailor CV -->
                <div id="modal-content-tailor" class="space-y-4 hidden">
                    <div class="flex items-center justify-between bg-zinc-950 p-3 rounded-xl border border-zinc-800">
                        <div>
                            <div class="font-bold text-white">İlana Özel Canonical LaTeX & ATS PDF CV</div>
                            <div class="text-zinc-400">Master CV şablonu ve Tectonic motoruyla üretilmiş LaTeX (.tex) ve vektör PDF.</div>
                        </div>
                        <div class="flex items-center gap-2">
                            <a id="btn-download-tex" href="#" target="_blank" class="px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-bold text-xs shadow-lg transition flex items-center gap-1.5">
                                <span>📄 .tex İndir</span>
                            </a>
                            <a id="btn-download-pdf" href="#" target="_blank" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold text-xs shadow-lg transition flex items-center gap-1.5">
                                <span>📑 PDF İndir</span>
                            </a>
                        </div>
                    </div>
                    <div id="tailor-results-box" class="space-y-3">
                        <div class="animate-pulse text-zinc-500">Laya modeli ile CV özelleştiriliyor...</div>
                    </div>
                </div>

                <!-- Sub-tab 3: Interview Prep -->
                <div id="modal-content-prep" class="space-y-4 hidden">
                    <div id="prep-results-box" class="space-y-3">
                        <div class="animate-pulse text-zinc-500">Mülakat kiti üretiliyor...</div>
                    </div>
                </div>

                <!-- Sub-tab 4: Culture Intelligence -->
                <div id="modal-content-culture" class="space-y-4 hidden">
                    <div id="culture-results-box" class="space-y-3">
                        <div class="animate-pulse text-zinc-500">Şirket ve kültür istihbaratı toplanıyor...</div>
                    </div>
                </div>
            </div>

            <!-- Modal Footer -->
            <div class="p-4 border-t border-zinc-800 bg-zinc-950 flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <span class="text-zinc-400">Durumu Değiştir:</span>
                    <select id="modal-status-select" onchange="updateActiveJobStatus(this.value)" class="bg-zinc-900 border border-zinc-800 rounded px-2.5 py-1 text-xs text-white">
                        <option value="inbox">Gelen Kutusu (Inbox)</option>
                        <option value="shortlisted">Kısa Liste (Shortlisted)</option>
                        <option value="interview_scheduled">Mülakat Planlandı 🎉</option>
                        <option value="assessment">Teknik Test 📝</option>
                        <option value="applied">Başvuruldu (Applied)</option>
                        <option value="archived">Elenen (Archived)</option>
                    </select>
                </div>
                <div class="flex items-center gap-2">
                    <a id="modal-apply-link" href="#" target="_blank" class="px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-semibold transition">İlana Git ↗</a>
                    <button onclick="closeModal()" class="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg">Kapat</button>
                </div>
            </div>
        </div>
    </div>

    <!-- JavaScript Logic -->
    <script>
        // Exported file:// dashboards target the default server port. Served dashboards use their own origin.
        const API_BASE = (window.location.protocol.startsWith('http') && window.location.host) ? '' : 'http://localhost:8080';
        let allJobs = [];
        let currentFilter = 'all';
        let activeJob = null;

        async function init() {
            await loadJobs();
            await loadProfile();
            await loadMasterCV();
            // Rehydrate the LinkedIn profile state on every page load, so a
            // hard refresh cannot leave a stale guest-mode badge.
            await checkSessionStatus();

            const texEditor = document.getElementById('latex-editor');
            if (texEditor) {
                texEditor.addEventListener('input', updateTexCharCount);
            }
        }

        async function loadMasterCV() {
            try {
                const res = await fetch(API_BASE + '/api/profile/master-tex');
                const data = await res.json();
                const editor = document.getElementById('latex-editor');
                if (editor && data.tex) {
                    editor.value = data.tex;
                    updateTexCharCount();
                }
            } catch (e) {
                console.error("Master CV yükleme hatası:", e);
            }
        }

        function updateTexCharCount() {
            const editor = document.getElementById('latex-editor');
            const countEl = document.getElementById('tex-char-count');
            if (editor && countEl) {
                const lineCount = editor.value.split(String.fromCharCode(10)).length;
                countEl.innerText = `${editor.value.length} karakter · ${lineCount} satır`;
            }
        }

        async function compileMasterTex() {
            const editor = document.getElementById('latex-editor');
            const btn = document.getElementById('btn-compile-tex');
            const alertBox = document.getElementById('latex-compile-alert');
            const badge = document.getElementById('pdf-status-badge');
            
            if (!editor) return;
            const texContent = editor.value;

            btn.disabled = true;
            btn.innerHTML = '<span>⚙️ Tectonic Derliyor...</span>';
            if (alertBox) {
                alertBox.className = 'p-3 rounded-lg text-xs font-mono bg-violet-950/60 text-violet-300 border border-violet-800/60 block';
                alertBox.innerText = '⏳ Tectonic derleyicisi çalıştırılıyor... Lütfen bekleyin.';
            }

            try {
                const res = await fetch(API_BASE + '/api/profile/compile-tex', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({tex: texContent})
                });
                const result = await res.json();
                if (result.success) {
                    if (alertBox) {
                        alertBox.className = 'p-3 rounded-lg text-xs font-mono bg-emerald-950/70 text-emerald-300 border border-emerald-800 block';
                        alertBox.innerText = '✅ Derleme başarılı! Vektörel PDF güncellendi.';
                    }
                    if (badge) {
                        badge.innerText = '🟢 Güncel';
                        badge.className = 'px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-mono';
                    }
                    reloadMasterPdf();
                } else {
                    if (alertBox) {
                        alertBox.className = 'p-3 rounded-lg text-xs font-mono bg-rose-950/70 text-rose-300 border border-rose-800 block overflow-x-auto whitespace-pre-wrap';
                        alertBox.innerText = '❌ Derleme Hatası: ' + (result.error || 'Bilinmeyen hata');
                    }
                    if (badge) {
                        badge.innerText = '🔴 Derleme Hatası';
                        badge.className = 'px-2 py-0.5 rounded text-[10px] bg-rose-950 text-rose-400 border border-rose-800 font-mono';
                    }
                }
            } catch (err) {
                if (alertBox) {
                    alertBox.className = 'p-3 rounded-lg text-xs font-mono bg-rose-950/70 text-rose-300 border border-rose-800 block';
                    alertBox.innerText = '❌ İstek Hatası: ' + err;
                }
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<span>⚡ Kaydet & Tectonic ile Derle</span>';
            }
        }

        function reloadMasterPdf() {
            const frame = document.getElementById('master-cv-pdf-frame');
            if (frame) {
                frame.src = `${API_BASE}/api/profile/master-pdf?t=${Date.now()}`;
            }
        }

        async function loadJobs() {
            try {
                const res = await fetch(API_BASE + '/api/jobs');
                allJobs = await res.json();
                updateStats();
                renderJobs();
                updateBatchCount();
            } catch (e) {
                console.error(e);
            }
        }

        async function loadProfile() {
            try {
                const res = await fetch(API_BASE + '/api/profile');
                const p = await res.json();
                document.getElementById('prof-name').value = p.name || '';
                document.getElementById('prof-title').value = p.title || '';
                document.getElementById('prof-email').value = p.email || '';
                document.getElementById('prof-phone').value = p.phone || '';
                document.getElementById('prof-linkedin').value = p.linkedin_url || '';
                document.getElementById('prof-summary').value = p.summary || '';
                document.getElementById('prof-skills').value = (p.core_skills || []).join(', ');
            } catch (e) {
                console.error(e);
            }
        }

        function updateStats() {
            document.getElementById('stat-total').innerText = allJobs.length;
            document.getElementById('stat-shortlisted').innerText = allJobs.filter(j => j.status === 'shortlisted').length;
            document.getElementById('stat-interview').innerText = allJobs.filter(j => j.status === 'interview_scheduled').length;
            document.getElementById('stat-assessment').innerText = allJobs.filter(j => j.status === 'assessment').length;
            document.getElementById('stat-applied').innerText = allJobs.filter(j => j.status === 'applied').length;
            document.getElementById('stat-archived').innerText = allJobs.filter(j => j.status === 'archived').length;
        }

        function updateBatchCount() {
            const short = allJobs.filter(j => j.status === 'shortlisted').length;
            const el = document.getElementById('batch-shortlist-count');
            if (el) el.innerText = `${short} İlan Hazır`;
        }

        function setFilter(status) {
            currentFilter = status;
            document.querySelectorAll('.filter-btn').forEach(btn => {
                if (btn.getAttribute('data-status') === status) {
                    btn.classList.add('bg-zinc-800', 'text-white');
                    btn.classList.remove('text-zinc-400');
                } else {
                    btn.classList.remove('bg-zinc-800', 'text-white');
                    btn.classList.add('text-zinc-400');
                }
            });
            renderJobs();
        }

        function renderJobs() {
            const q = (document.getElementById('search-input').value || '').toLowerCase();
            const container = document.getElementById('jobs-container');

            const filtered = allJobs.filter(j => {
                if (currentFilter !== 'all' && j.status !== currentFilter) return false;
                if (q) {
                    const matchText = `${j.job.title} ${j.job.company} ${j.job.location}`.toLowerCase();
                    if (!matchText.includes(q)) return false;
                }
                return true;
            });

            if (filtered.length === 0) {
                container.innerHTML = '<div class="col-span-full py-12 text-center text-zinc-500 text-xs">Bu kritere uygun ilan bulunamadı.</div>';
                return;
            }

            container.innerHTML = filtered.map(item => {
                const j = item.job;
                const m = item.match;
                const score = Math.round((m.fit_score || 0) * 100);
                
                let scoreBg = 'from-violet-500 to-indigo-600';
                if (score >= 85) scoreBg = 'from-emerald-500 to-teal-500';
                else if (score < 60) scoreBg = 'from-amber-500 to-orange-500';

                let statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400 font-mono">${item.status}</span>`;
                if (item.status === 'shortlisted') statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-violet-950 text-violet-300 border border-violet-800 font-mono">⭐ Shortlist</span>`;
                else if (item.status === 'interview_scheduled') statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 font-mono">🎉 Mülakat</span>`;
                else if (item.status === 'assessment') statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-800 font-mono">📝 Test</span>`;
                else if (item.status === 'applied') statusBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-blue-950 text-blue-300 border border-blue-800 font-mono">📬 Başvuruldu</span>`;

                return `
                <div onclick="openJobDetail('${j.id}')" class="cursor-pointer bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800/80 hover:border-zinc-700 p-4 rounded-xl transition flex flex-col justify-between space-y-3 group shadow-lg">
                    <div>
                        <div class="flex items-start justify-between gap-2">
                            <span class="text-xs font-semibold text-zinc-400 truncate">${escapeHtml(j.company)}</span>
                            ${statusBadge}
                        </div>
                        <h4 class="font-bold text-white text-sm mt-1 group-hover:text-violet-400 transition leading-snug">${escapeHtml(j.title)}</h4>
                        <div class="text-[11px] text-zinc-500 mt-0.5">${escapeHtml(j.location || 'Remote')}</div>
                    </div>

                    <div class="space-y-1.5 pt-2 border-t border-zinc-800/60">
                        <div class="flex justify-between items-center text-xs">
                            <span class="text-zinc-400 font-medium">Eşleşme</span>
                            <span class="font-bold text-white">%${score}</span>
                        </div>
                        <div class="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                            <div class="h-full bg-gradient-to-r ${scoreBg} rounded-full" style="width: ${score}%"></div>
                        </div>
                    </div>
                </div>
                `;
            }).join('');
        }

        function switchTab(tab) {
            ['feed', 'outreach', 'inbox', 'batch', 'hunt', 'profile'].forEach(t => {
                document.getElementById(`tab-${t}`).classList.add('hidden');
                const btn = document.getElementById(`nav-${t}`);
                if (btn) {
                    btn.classList.remove('bg-zinc-800', 'text-white');
                    btn.classList.add('text-zinc-400');
                }
            });
            document.getElementById(`tab-${tab}`).classList.remove('hidden');
            const activeBtn = document.getElementById(`nav-${tab}`);
            if (activeBtn) {
                activeBtn.classList.add('bg-zinc-800', 'text-white');
                activeBtn.classList.remove('text-zinc-400');
            }

            if (tab === 'outreach') loadOutreachSteps();
            if (tab === 'inbox') loadEmailEvents();
            if (tab === 'batch') updateBatchCount();
            if (tab === 'hunt') checkSessionStatus();
            if (tab === 'profile') loadMasterCV();
        }

        async function loadOutreachSteps() {
            const container = document.getElementById('outreach-container');
            container.innerHTML = '<div class="text-xs text-zinc-500">Yükleniyor...</div>';
            try {
                const res = await fetch(API_BASE + '/api/sequences');
                const steps = await res.json();
                if (steps.length === 0) {
                    container.innerHTML = '<div class="p-8 text-center text-zinc-500 text-xs bg-zinc-900 border border-zinc-800 rounded-xl">Henüz oluşturulmuş takip dizisi yok. Bir ilanın detayından iletişim dizisi üretebilirsiniz.</div>';
                    return;
                }

                container.innerHTML = steps.map(s => `
                    <div class="bg-zinc-900 border border-zinc-800 p-4 rounded-xl space-y-3">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center gap-2">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${s.step_day === 0 ? 'bg-violet-950 text-violet-300 border border-violet-800' : (s.step_day === 5 ? 'bg-indigo-950 text-indigo-300 border border-indigo-800' : 'bg-emerald-950 text-emerald-300 border border-emerald-800')}">DAY ${s.step_day} (${s.channel.toUpperCase()})</span>
                                <span class="font-bold text-white text-xs">${escapeHtml(s.subject)}</span>
                            </div>
                            <span class="text-[10px] font-mono px-2 py-0.5 rounded ${s.status === 'approved' ? 'bg-emerald-950 text-emerald-300' : (s.status === 'sent' ? 'bg-blue-950 text-blue-300' : 'bg-amber-950 text-amber-300')}">${s.status.toUpperCase()}</span>
                        </div>
                        <div class="p-3 bg-zinc-950 rounded-lg text-zinc-300 font-mono text-[11px] whitespace-pre-line border border-zinc-800/80">${escapeHtml(s.body)}</div>
                        <div class="flex justify-end gap-2 text-xs">
                            ${s.status === 'draft' ? `<button onclick="approveOutreachStep('${s.id}')" class="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-medium">✓ Onayla (Approve)</button>` : ''}
                            ${s.status === 'approved' ? `<button onclick="markOutreachSent('${s.id}')" class="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded font-medium">İletildi Olarak İşaretle</button>` : ''}
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                container.innerHTML = `<div class="text-rose-400 text-xs">Hata: ${e}</div>`;
            }
        }

        async function approveOutreachStep(stepId) {
            await fetch(API_BASE + '/api/sequences/approve', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({step_id: stepId})
            });
            await loadOutreachSteps();
        }

        async function markOutreachSent(stepId) {
            await fetch(API_BASE + '/api/sequences/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({step_id: stepId, status: 'sent'})
            });
            await loadOutreachSteps();
        }

        async function loadEmailEvents() {
            const container = document.getElementById('email-events-container');
            container.innerHTML = '<div class="text-xs text-zinc-500">Yükleniyor...</div>';
            try {
                const res = await fetch(API_BASE + '/api/email-events');
                const events = await res.json();
                if (events.length === 0) {
                    container.innerHTML = '<div class="p-8 text-center text-zinc-500 text-xs bg-zinc-900 border border-zinc-800 rounded-xl">Henüz işlenmiş e-posta olayı yok. Yukarıdaki butona tıklayarak örnek mülakat davetini simüle edebilirsiniz.</div>';
                    return;
                }

                container.innerHTML = events.map(ev => {
                    let catBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400">${ev.category}</span>`;
                    if (ev.category === 'interview_invitation') catBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">🎉 Mülakat Daveti</span>`;
                    else if (ev.category === 'assessment_test') catBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">📝 Teknik Değerlendirme</span>`;
                    else if (ev.category === 'rejection') catBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-800 font-bold">❌ Red Bildirimi</span>`;
                    else if (ev.category === 'application_received') catBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-blue-950 text-blue-300 border border-blue-800 font-bold">📬 Başvuru Alındı</span>`;

                    return `
                        <div class="bg-zinc-900 border border-zinc-800 p-3.5 rounded-xl space-y-2">
                            <div class="flex items-center justify-between">
                                <div class="flex items-center gap-2">
                                    ${catBadge}
                                    <span class="font-bold text-white text-xs">${escapeHtml(ev.subject)}</span>
                                </div>
                                <span class="text-[10px] text-zinc-500 font-mono">${ev.received_at.split('T')[0]}</span>
                            </div>
                            <div class="text-[11px] text-zinc-400 flex items-center gap-2">
                                <span>Gönderen: <strong class="text-zinc-300">${escapeHtml(ev.sender)}</strong></span>
                                ${ev.matched_company ? `<span>• Şirket: <strong class="text-violet-400">${escapeHtml(ev.matched_company)}</strong></span>` : ''}
                            </div>
                            <div class="p-2.5 bg-zinc-950 rounded text-zinc-300 text-xs font-mono border border-zinc-800/80">${escapeHtml(ev.body_snippet)}</div>
                            ${ev.action_taken ? `<div class="text-[10px] text-emerald-400 font-mono">⚡ Aksiyon: ${escapeHtml(ev.action_taken)}</div>` : ''}
                        </div>
                    `;
                }).join('');
            } catch (e) {
                container.innerHTML = `<div class="text-rose-400 text-xs">Hata: ${e}</div>`;
            }
        }

        async function simulateMockEmail() {
            try {
                const res = await fetch(API_BASE + '/api/email-triage/mock', {method: 'POST'});
                await loadEmailEvents();
                await loadJobs();
                alert('Örnek mülakat daveti e-postası yerel Laya modeli ile işlendi ve iş durumu güncellendi!');
            } catch (e) {
                alert(`Hata: ${e}`);
            }
        }

        async function triggerBatchApply() {
            const headful = document.getElementById('batch-headful').checked;
            const limit = parseInt(document.getElementById('batch-limit').value || '3');
            const progressBox = document.getElementById('batch-progress-box');
            const btn = document.getElementById('btn-batch-apply');

            btn.disabled = true;
            btn.classList.add('opacity-50');
            progressBox.classList.remove('hidden');

            try {
                const res = await fetch(API_BASE + '/api/batch-apply', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({limit: limit, headful: headful})
                });
                const result = await res.json();
                alert(`Form hazırlığı tamamlandı. Otomatik başvuru gönderilmedi. İnceleme gereken: ${result.failed_count}`);
                await loadJobs();
            } catch (e) {
                alert(`Hata: ${e}`);
            } finally {
                btn.disabled = false;
                btn.classList.remove('opacity-50');
                progressBox.classList.add('hidden');
            }
        }

        async function openJobDetail(jobId) {
            activeJob = allJobs.find(j => j.job.id === jobId);
            if (!activeJob) return;

            document.getElementById('modal-title').innerText = activeJob.job.title;
            document.getElementById('modal-subtitle').innerText = `${activeJob.job.company} • ${activeJob.job.location || 'Remote'}`;
            document.getElementById('modal-desc-body').innerText = activeJob.job.description;
            document.getElementById('modal-status-select').value = activeJob.status;
            document.getElementById('modal-apply-link').href = activeJob.job.url;
            document.getElementById('btn-download-tex').href = `${API_BASE}/api/resume/download?job_id=${activeJob.job.id}&format=tex`;
            document.getElementById('btn-download-pdf').href = `${API_BASE}/api/resume/download?job_id=${activeJob.job.id}&format=pdf`;

            switchModalTab('desc');
            document.getElementById('modal-detail').classList.remove('hidden');
        }

        async function switchModalTab(tab) {
            ['desc', 'tailor', 'prep', 'culture'].forEach(t => {
                document.getElementById(`modal-content-${t}`).classList.add('hidden');
                document.getElementById(`modal-tab-${t}`).classList.remove('text-violet-400', 'border-b-2', 'border-violet-500');
                document.getElementById(`modal-tab-${t}`).classList.add('text-zinc-400');
            });
            document.getElementById(`modal-content-${tab}`).classList.remove('hidden');
            document.getElementById(`modal-tab-${tab}`).classList.add('text-violet-400', 'border-b-2', 'border-violet-500');
            document.getElementById(`modal-tab-${tab}`).classList.remove('text-zinc-400');

            if (tab === 'tailor') loadTailorData();
            if (tab === 'prep') loadPrepData();
            if (tab === 'culture') loadCultureData();
        }

        async function loadTailorData() {
            if (!activeJob) return;
            const box = document.getElementById('tailor-results-box');
            box.innerHTML = '<div class="animate-pulse text-zinc-500">Laya modeli ile CV özelleştiriliyor...</div>';
            try {
                const res = await fetch(API_BASE + '/api/tailor', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({job_id: activeJob.job.id})
                });
                const t = await res.json();
                box.innerHTML = `
                    <div class="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-2">
                        <span class="text-xs font-semibold text-violet-400">Hedef Unvan</span>
                        <div class="font-bold text-white text-sm">${escapeHtml(t.tailored_headline || '')}</div>
                    </div>
                    <div class="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-2">
                        <span class="text-xs font-semibold text-emerald-400">Özelleştirilmiş Özet</span>
                        <div class="text-zinc-300 leading-relaxed">${escapeHtml(t.tailored_summary || '')}</div>
                    </div>
                    <div class="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-2">
                        <span class="text-xs font-semibold text-cyan-400">Öne Çıkan Başarı Maddeleri</span>
                        <ul class="list-disc pl-4 text-zinc-300 space-y-1">
                            ${(t.tailored_bullets || []).map(b => `<li>${escapeHtml(b)}</li>`).join('')}
                        </ul>
                    </div>
                `;
            } catch (e) {
                box.innerHTML = `<div class="text-rose-400 text-xs">Hata: ${e}</div>`;
            }
        }

        async function loadPrepData() {
            if (!activeJob) return;
            const box = document.getElementById('prep-results-box');
            box.innerHTML = '<div class="animate-pulse text-zinc-500">Mülakat ve iletişim kiti hazırlanıyor...</div>';
            try {
                const res = await fetch(API_BASE + '/api/interview-prep', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({job_id: activeJob.job.id})
                });
                const p = await res.json();
                box.innerHTML = `
                    <div class="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-3">
                        <div class="flex justify-between items-center">
                            <span class="text-xs font-semibold text-violet-400">LinkedIn InMail Notu (&lt;300 Karakter)</span>
                            <button onclick="copyToClipboard('inmail-note')" class="text-xs text-zinc-400 hover:text-white">Kopyala</button>
                        </div>
                        <div id="inmail-note" class="p-3 bg-zinc-900 rounded font-mono text-zinc-200 text-xs">${escapeHtml(p.connection_note)}</div>
                    </div>
                    <div class="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-3">
                        <span class="text-xs font-semibold text-cyan-400">5 Teknik Mülakat Sorusu & Konuşma Noktaları</span>
                        <div class="space-y-3">
                            ${(p.technical_questions || []).map((q, i) => `
                                <div class="p-3 bg-zinc-900 rounded space-y-1">
                                    <div class="font-bold text-white text-xs">${i+1}. ${escapeHtml(q.question)}</div>
                                    <div class="text-zinc-400 text-[11px]">${escapeHtml(q.talking_points)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            } catch (e) {
                box.innerHTML = `<div class="text-rose-400 text-xs">Hata: ${e}</div>`;
            }
        }

        async function loadCultureData() {
            if (!activeJob) return;
            const box = document.getElementById('culture-results-box');
            box.innerHTML = '<div class="animate-pulse text-zinc-500">Şirket kültür istihbaratı ve GitHub sinyalleri toplanıyor...</div>';
            try {
                const res = await fetch(API_BASE + '/api/culture/analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({job_id: activeJob.job.id, company: activeJob.job.company})
                });
                const c = await res.json();
                const scorePct = Math.round((c.culture_score || 0.8) * 100);
                box.innerHTML = `
                    <div class="grid grid-cols-3 gap-3">
                        <div class="bg-zinc-950 p-3 rounded-xl border border-zinc-800">
                            <div class="text-zinc-500 text-[10px]">Kültür Skoru</div>
                            <div class="text-lg font-bold text-emerald-400 mt-0.5">%${scorePct}</div>
                        </div>
                        <div class="bg-zinc-950 p-3 rounded-xl border border-zinc-800">
                            <div class="text-zinc-500 text-[10px]">Tech Debt Riski</div>
                            <div class="text-lg font-bold ${c.tech_debt_risk === 'low' ? 'text-emerald-400' : 'text-amber-400'} mt-0.5">${c.tech_debt_risk.toUpperCase()}</div>
                        </div>
                        <div class="bg-zinc-950 p-3 rounded-xl border border-zinc-800">
                            <div class="text-zinc-500 text-[10px]">Tahmini Maaş Seviyesi</div>
                            <div class="text-xs font-bold text-violet-400 mt-1">${escapeHtml(c.estimated_salary_range)}</div>
                        </div>
                    </div>
                    <div class="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-2">
                        <span class="text-xs font-semibold text-emerald-400">Öne Çıkan Pozitif Kültür Göstergeleri</span>
                        <ul class="list-disc pl-4 text-zinc-300 space-y-1">
                            ${(c.highlights || []).map(h => `<li>${escapeHtml(h)}</li>`).join('')}
                        </ul>
                    </div>
                    ${c.red_flags && c.red_flags.length > 0 ? `
                        <div class="bg-zinc-950 p-4 rounded-xl border border-rose-900/50 space-y-2">
                            <span class="text-xs font-semibold text-rose-400">Dikkat Edilmesi Gereken Risk / Red Flag Sinyalleri</span>
                            <ul class="list-disc pl-4 text-rose-300 space-y-1">
                                ${(c.red_flags).map(rf => `<li>${escapeHtml(rf)}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                `;
            } catch (e) {
                box.innerHTML = `<div class="text-rose-400 text-xs">Hata: ${e}</div>`;
            }
        }

        function copyToClipboard(id) {
            const text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text);
            alert('Panoya kopyalandı!');
        }

        async function updateActiveJobStatus(status) {
            if (!activeJob) return;
            await fetch(API_BASE + '/api/jobs/status', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: activeJob.job.id, status: status})
            });
            activeJob.status = status;
            await loadJobs();
        }

        function closeModal() {
            document.getElementById('modal-detail').classList.add('hidden');
            activeJob = null;
        }

        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function syncFiltersToUrl() {
            const kw = encodeURIComponent(document.getElementById('filter-keywords').value.trim() || 'Python Backend');
            const loc = encodeURIComponent(document.getElementById('filter-location').value.trim());
            const wtCodes = [];
            if (document.getElementById('filter-wt-onsite').checked) wtCodes.push('1');
            if (document.getElementById('filter-wt-remote').checked) wtCodes.push('2');
            if (document.getElementById('filter-wt-hybrid').checked) wtCodes.push('3');
            const dateVal = document.getElementById('filter-date').value;
            const easyApply = document.getElementById('filter-easy-apply').checked;
            const experienceMap = [
                ['filter-exp-intern', '1'], ['filter-exp-entry', '2'],
                ['filter-exp-associate', '3'], ['filter-exp-mid', '4'],
                ['filter-exp-director', '5'], ['filter-exp-executive', '6']
            ];
            const experienceCodes = experienceMap
                .filter(([id]) => document.getElementById(id).checked)
                .map(([, code]) => code);

            const params = new URLSearchParams({keywords: document.getElementById('filter-keywords').value.trim() || 'Python Backend'});
            if (loc) params.set('location', document.getElementById('filter-location').value.trim());
            let url = `https://www.linkedin.com/jobs/search-results/?${params.toString()}`;
            if (wtCodes.length > 0) {
                url += `&f_WT=${encodeURIComponent(wtCodes.join(','))}`;
            }
            if (dateVal && dateVal !== 'all') {
                url += `&f_TPR=${dateVal}`;
            }
            if (easyApply) {
                url += `&f_AL=true`;
            }
            if (experienceCodes.length > 0) {
                url += `&f_E=${encodeURIComponent(experienceCodes.join(','))}`;
            }

            document.getElementById('hunt-url').value = url;
        }

        async function checkSessionStatus() {
            const badge = document.getElementById('session-status-badge');
            if (!badge) return;
            try {
                const res = await fetch(API_BASE + '/api/hunt/session-status');
                const data = await res.json();
                if (data.logged_in) {
                    badge.innerText = '🟢 LinkedIn Oturumu Açık';
                    badge.className = 'px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800 font-mono';
                } else if (data.browser_open) {
                    // A live Chrome profile is the authoritative session owner.
                    // SQLite may lag or omit Chromium's encrypted auth cookie
                    // while the browser is running, so do not downgrade it to
                    // guest mode after refresh.
                    badge.innerText = '🟡 Chrome açık · Oturum canlı doğrulanamıyor';
                    badge.className = 'px-2 py-0.5 rounded text-[10px] bg-amber-950/80 text-amber-400 border border-amber-800 font-mono';
                } else {
                    badge.innerText = '🟡 Misafir Modu (Giriş Yok)';
                    badge.className = 'px-2 py-0.5 rounded text-[10px] bg-amber-950/80 text-amber-400 border border-amber-800 font-mono';
                }
            } catch(e) {
                badge.innerText = '⚪ Durum Alınamadı';
            }
        }

        function setHuntPreset(type) {
            const input = document.getElementById('hunt-url');
            if (type === 'linkedin_tr') {
                document.getElementById('filter-keywords').value = 'Python Backend';
                document.getElementById('filter-location').value = 'Turkey';
                document.getElementById('filter-wt-remote').checked = true;
                document.getElementById('filter-wt-hybrid').checked = true;
                document.getElementById('filter-wt-onsite').checked = false;
                syncFiltersToUrl();
            } else if (type === 'linkedin_ai') {
                document.getElementById('filter-keywords').value = 'AI Engineer Agent';
                document.getElementById('filter-location').value = 'Worldwide';
                document.getElementById('filter-wt-remote').checked = true;
                document.getElementById('filter-wt-hybrid').checked = false;
                document.getElementById('filter-wt-onsite').checked = false;
                syncFiltersToUrl();
            } else if (type === 'wwr_backend') {
                input.value = 'https://weworkremotely.com/categories/remote-programming-jobs';
            }
        }

        async function triggerLogin() {
            if (!confirm('LinkedIn giriş penceresi açılacak. Ekrana gelen pencerede hesabınıza giriş yapın (2FA varsa tamamlayın). Giriş yapıldığında sistem oturumu otomatik algılayacaktır. Devam edilsin mi?')) return;
            try {
                const res = await fetch(API_BASE + '/api/hunt/login', {method: 'POST'});
                const data = await res.json();
                
                // Poll session status periodically
                let pollCount = 0;
                const sessionInterval = setInterval(async () => {
                    pollCount++;
                    await checkSessionStatus();
                    const badge = document.getElementById('session-status-badge');
                    if (badge && badge.innerText.includes('🟢') || pollCount > 100) {
                        clearInterval(sessionInterval);
                    }
                }, 3000);
            } catch(e) {
                alert('Giriş oturumu açılamadı: ' + e);
            }
        }

        let huntPollTimer = null;
        let seenJobIds = new Set();

        async function triggerHunt() {
            const url = document.getElementById('hunt-url').value.trim();
            const max = parseInt(document.getElementById('hunt-max').value || '5');
            const headful = document.getElementById('hunt-headful').checked;
            const btn = document.getElementById('btn-hunt');
            const consoleWrapper = document.getElementById('hunt-console-wrapper');
            const consoleBox = document.getElementById('hunt-console');
            const indicator = document.getElementById('hunt-status-indicator');

            if (!url) {
                alert("Lütfen geçerli bir arama URL'si girin.");
                return;
            }

            btn.disabled = true;
            document.getElementById('btn-stop-hunt').disabled = false;
            btn.innerHTML = '<span class="animate-spin inline-block mr-2">⚙️</span> Ajan Çalışıyor (Taranıyor)...';
            consoleWrapper.classList.remove('hidden');
            consoleBox.innerHTML = '<div class="text-zinc-500">Ajan başlatılıyor... Playwright ve Laya hazırlanıyor.</div>';
            indicator.innerText = 'Çalışıyor...';
            indicator.className = 'text-emerald-400 font-mono text-[11px] animate-pulse';

            // Hide empty placeholder
            const placeholder = document.getElementById('hunt-empty-placeholder');
            if (placeholder) placeholder.classList.add('hidden');

            try {
                // Trigger hunt on backend (runs asynchronously in background worker)
                const res = await fetch(API_BASE + '/api/hunt', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, max_jobs: max, headful: headful})
                });
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.message || `Sunucu hatası: ${res.status}`);
                }

                // Start polling logs and discovered jobs
                if (huntPollTimer) clearInterval(huntPollTimer);
                huntPollTimer = setInterval(pollHuntProgress, 800);
            } catch (e) {
                alert(`Hata oluştu: ${e.message || e}`);
                btn.disabled = false;
                btn.innerHTML = "<span>🚀 LinkedIn'de Otomatik Avı Başlat</span>";
                indicator.innerText = 'Hata oluştu';
                indicator.className = 'text-rose-400 font-mono text-[11px]';
                document.getElementById('btn-stop-hunt').disabled = true;
            }
        }

        async function stopHunt() {
            const stopBtn = document.getElementById('btn-stop-hunt');
            stopBtn.disabled = true;
            stopBtn.innerText = 'Durduruluyor…';
            try {
                const res = await fetch(API_BASE + '/api/hunt/stop', {method: 'POST'});
                if (!res.ok) throw new Error(`Durdurma isteği başarısız: ${res.status}`);
                stopBtn.innerText = 'Durdurma istendi';
            } catch (e) {
                console.error('Arama durdurma isteği başarısız:', e);
                stopBtn.disabled = false;
                stopBtn.innerText = 'Aramayı Durdur';
            }
        }

        async function pollHuntProgress() {
            try {
                const res = await fetch(API_BASE + '/api/hunt/logs');
                const data = await res.json();
                const consoleBox = document.getElementById('hunt-console');
                const cardsContainer = document.getElementById('hunt-live-cards');
                const countBadge = document.getElementById('hunt-found-count');
                const indicator = document.getElementById('hunt-status-indicator');
                const btn = document.getElementById('btn-hunt');

                // 1. Render logs in console
                if (data.logs && data.logs.length > 0) {
                    consoleBox.innerHTML = data.logs.map(line => {
                        let colorClass = 'text-zinc-300';
                        if (line.includes('✅') || line.includes('🎯') || line.includes('Başarılı')) colorClass = 'text-emerald-400';
                        else if (line.includes('🤖') || line.includes('⭐')) colorClass = 'text-violet-300';
                        else if (line.includes('⚠️') || line.includes('Elendi')) colorClass = 'text-amber-400';
                        else if (line.includes('❌') || line.includes('Hata')) colorClass = 'text-rose-400';
                        else if (line.includes('🔍') || line.includes('👉')) colorClass = 'text-blue-300';
                        return `<div class="${colorClass}">${escapeHtml(line)}</div>`;
                    }).join('');
                    consoleBox.scrollTop = consoleBox.scrollHeight;
                }

                // 2. Render discovered jobs stream
                if (data.jobs && data.jobs.length > 0) {
                    countBadge.innerText = `${data.jobs.length} İlan`;
                    
                    data.jobs.forEach(item => {
                        const j = item.job;
                        if (!seenJobIds.has(j.id)) {
                            seenJobIds.add(j.id);
                            
                            const score = Math.round((item.match ? item.match.fit_score : 0) * 100);
                            let scoreBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400 font-mono">%${score}</span>`;
                            let borderClass = 'border-zinc-800';
                            if (score >= 70) {
                                scoreBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-violet-950 text-violet-300 border border-violet-800 font-mono font-bold">⭐ %${score} UYGUN</span>`;
                                borderClass = 'border-violet-800/80 bg-violet-950/20';
                            } else if (score >= 50) {
                                scoreBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-blue-950 text-blue-300 border border-blue-800 font-mono font-bold">📬 %${score} İnceleme</span>`;
                                borderClass = 'border-blue-800/60 bg-blue-950/20';
                            } else {
                                scoreBadge = `<span class="px-2 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-500 font-mono">%${score} Düşük</span>`;
                            }

                            const card = document.createElement('div');
                            card.className = `p-4 rounded-xl border ${borderClass} bg-zinc-900/90 shadow-lg space-y-3 transition transform animate-fade-in`;
                            card.innerHTML = `
                                <div class="flex items-start justify-between gap-3">
                                    <div>
                                        <div class="text-xs font-semibold text-zinc-400">${escapeHtml(j.company)} • ${escapeHtml(j.location || 'Remote')}</div>
                                        <h4 class="font-bold text-white text-sm mt-0.5">${escapeHtml(j.title)}</h4>
                                    </div>
                                    <div class="text-right flex flex-col items-end gap-1">
                                        ${scoreBadge}
                                        <span class="text-[10px] text-zinc-500">${item.status.toUpperCase()}</span>
                                    </div>
                                </div>
                                <div class="text-xs text-zinc-300 bg-zinc-950/80 p-2.5 rounded-lg border border-zinc-800/60 leading-relaxed">
                                    <div class="font-medium text-zinc-400 text-[11px] mb-1">🤖 Laya Değerlendirmesi:</div>
                                    <div>${escapeHtml(item.match ? item.match.reasoning : (j.description ? j.description.slice(0, 180) + '...' : ''))}</div>
                                </div>
                                <div class="flex items-center justify-between pt-1">
                                    <div class="flex items-center gap-2">
                                        <a href="${j.url}" target="_blank" class="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded text-[11px] font-medium transition flex items-center gap-1">
                                            <span>🔗 İlanı Aç</span>
                                        </a>
                                        <a href="${API_BASE}/api/resume/download?job_id=${j.id}&format=tex" target="_blank" class="px-2.5 py-1 bg-indigo-950 hover:bg-indigo-900 text-indigo-300 border border-indigo-800 rounded text-[11px] font-medium transition flex items-center gap-1">
                                            <span>📄 .tex</span>
                                        </a>
                                        <a href="${API_BASE}/api/resume/download?job_id=${j.id}&format=pdf" target="_blank" class="px-2.5 py-1 bg-emerald-950 hover:bg-emerald-900 text-emerald-300 border border-emerald-800 rounded text-[11px] font-medium transition flex items-center gap-1">
                                            <span>📑 PDF</span>
                                        </a>
                                    </div>
                                    <button onclick="openJobDetail('${j.id}')" class="text-violet-400 hover:text-violet-300 text-xs font-semibold">
                                        Detay & Mülakat Kiti →
                                    </button>
                                </div>
                            `;
                            // Prepend card to top of list
                            cardsContainer.prepend(card);
                        }
                    });
                }

                // 3. Check if hunt finished
                if (!data.is_running) {
                    if (huntPollTimer) {
                        clearInterval(huntPollTimer);
                        huntPollTimer = null;
                    }
                    indicator.innerText = data.last_message || 'Tamamlandı';
                    indicator.className = 'text-zinc-400 font-mono text-[11px]';
                    btn.disabled = false;
                    btn.innerHTML = "<span>🚀 LinkedIn'de Otomatik Avı Başlat</span>";
                    const stopBtn = document.getElementById('btn-stop-hunt');
                    stopBtn.disabled = true;
                    stopBtn.innerText = 'Aramayı Durdur';
                    await loadJobs(); // Refresh main feed as well
                }
            } catch (err) {
                console.error("Poll error:", err);
            }
        }

        async function clearAllData() {
            if (!confirm('Tüm kayıtlı ilan geçmişi sıfırlanacak. Emin misiniz?')) return;
            try {
                await fetch(API_BASE + '/api/clear-all', {method: 'POST'});
                seenJobIds.clear();
                const cardsContainer = document.getElementById('hunt-live-cards');
                cardsContainer.innerHTML = '<div id="hunt-empty-placeholder" class="text-center py-8 text-xs text-zinc-500 bg-zinc-950/50 rounded-xl border border-dashed border-zinc-800">Veriler sıfırlandı. Yeni bir av başlatabilirsiniz.</div>';
                document.getElementById('hunt-found-count').innerText = '0 İlan';
                document.getElementById('hunt-console').innerHTML = '<div class="text-zinc-600">Geçmiş temizlendi. Yeni av bekleniyor...</div>';
                await loadJobs();
                alert('Tüm veriler başarıyla sıfırlandı!');
            } catch(e) {
                alert('Sıfırlama hatası: ' + e);
            }
        }

        async function saveProfile() {
            const p = {
                name: document.getElementById('prof-name').value,
                title: document.getElementById('prof-title').value,
                email: document.getElementById('prof-email').value,
                phone: document.getElementById('prof-phone').value,
                linkedin_url: document.getElementById('prof-linkedin').value,
                summary: document.getElementById('prof-summary').value,
                core_skills: document.getElementById('prof-skills').value.split(',').map(s => s.trim()).filter(Boolean)
            };
            await fetch(API_BASE + '/api/profile', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(p)
            });
            alert('Profil güncellendi!');
        }

        init();
    </script>
</body>
</html>
"""


class DashboardServer:
    """Lightweight HTTP server with REST APIs, PDF rendering, email watcher, and batch application."""

    def __init__(
        self,
        storage: LocalBrainStorage,
        profile: Optional[CandidateProfile] = None,
        port: int = 8080,
    ):
        self.storage = storage
        self.profile = profile or CandidateProfile()
        self.port = port
        self.laya_client = LayaClient()
        self.tailor = CVTailor(self.laya_client)
        self.pdf_gen = PDFResumeGenerator()
        self.prep_assistant = InterviewPrepAssistant(self.laya_client)
        self.sequencer = OutreachSequencer(self.storage)
        self.culture_agent = CompanyCultureAgent(self.laya_client, self.storage)
        self.email_watcher = EmailInboxWatcher(self.laya_client, self.storage)
        self.batch_orchestrator = BatchApplyOrchestrator(self.laya_client, self.storage)

    def export_html(self, output_path: str = "job_hunter_dashboard.html") -> str:
        content = render_dashboard_html()
        path = Path(output_path)
        path.write_text(content, encoding="utf-8")
        return str(path.resolve())

    def run(self):
        storage = self.storage
        profile = self.profile
        tailor = self.tailor
        pdf_gen = self.pdf_gen
        prep_assistant = self.prep_assistant
        sequencer = self.sequencer
        culture_agent = self.culture_agent
        email_watcher = self.email_watcher
        batch_orchestrator = self.batch_orchestrator
        laya_client = self.laya_client

        class Handler(http.server.BaseHTTPRequestHandler):
            def _send_cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

            def do_OPTIONS(self):
                self.send_response(204)
                self._send_cors_headers()
                self.end_headers()

            def do_HEAD(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()

            def _json(self, data, status: int = 200):
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))

            def _html(self, content: str, status: int = 200):
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                params = urllib.parse.parse_qs(parsed.query)

                if path in ("/", "/index.html"):
                    self._html(render_dashboard_html())

                elif path == "/api/jobs":
                    self._json([j.to_dict() for j in storage.list_jobs()])

                elif path == "/api/sequences":
                    self._json([s.to_dict() for s in storage.list_outreach_steps()])

                elif path == "/api/email-events":
                    self._json([e.to_dict() for e in storage.list_email_events()])

                elif path == "/api/profile":
                    self._json(profile.to_dict())

                elif path == "/api/profile/master-tex":
                    tex_file = Path("candidate/base_cv.tex")
                    content = tex_file.read_text(encoding="utf-8") if tex_file.exists() else ""
                    self._json({"tex": content})
                    return

                elif path == "/api/profile/master-tex/download":
                    tex_file = Path("candidate/base_cv.tex")
                    if tex_file.exists():
                        self.send_response(200)
                        self.send_header("Content-Type", "text/x-tex; charset=utf-8")
                        self.send_header("Content-Disposition", 'attachment; filename="candidate/base_cv.tex"')
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(tex_file.read_bytes())
                        return
                    self.send_response(404)
                    self._send_cors_headers()
                    self.end_headers()
                    return

                elif path == "/api/profile/master-pdf":
                    pdf_file = Path("candidate/base_cv.pdf")
                    is_dl = "true" in params.get("download", ["false"])
                    if not pdf_file.exists():
                        import subprocess
                        import shutil
                        tex_file = Path("candidate/base_cv.tex")
                        tectonic_bin = "/opt/homebrew/bin/tectonic"
                        if not Path(tectonic_bin).exists():
                            tectonic_bin = shutil.which("tectonic") or "tectonic"
                        if tex_file.exists():
                            subprocess.run([tectonic_bin, str(tex_file), "--outdir", "candidate"], check=False)
                    if pdf_file.exists():
                        self.send_response(200)
                        self.send_header("Content-Type", "application/pdf")
                        disp = "attachment" if is_dl else "inline"
                        self.send_header("Content-Disposition", f'{disp}; filename="candidate/base_cv.pdf"')
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(pdf_file.read_bytes())
                        return
                    self.send_response(404)
                    self._send_cors_headers()
                    self.end_headers()
                    return

                elif path == "/api/hunt/status":
                    self._json(_hunt_state)
                    return

                elif path == "/api/hunt/stop":
                    if _hunt_state["is_running"]:
                        _hunt_cancel_event.set()
                        add_hunt_log("⏹️ Durdurma isteği alındı; mevcut tarayıcı adımı tamamlanınca duracak.")
                        self._json({"success": True, "message": "Durdurma istendi."})
                    else:
                        self._json({"success": False, "message": "Çalışan arama yok."}, status=409)
                    return

                elif path == "/api/hunt/session-status":
                    from job_hunter.navigator import BrowserNavigator
                    nav = BrowserNavigator(laya_client, headless=True)
                    logged_in = nav.check_linkedin_session()
                    profile_dir = Path(DEFAULT_CHROME_PROFILE_DIR)
                    lock = profile_dir / "SingletonLock"
                    browser_open = False
                    if lock.is_symlink():
                        try:
                            owner = lock.resolve(strict=False).name.rsplit("-", 1)[-1]
                            if owner.isdigit():
                                import os
                                os.kill(int(owner), 0)
                                browser_open = True
                        except (ProcessLookupError, FileNotFoundError):
                            pass
                        except PermissionError:
                            browser_open = True
                    if browser_open:
                        # Read the live browser context when available; the
                        # on-disk Cookies DB may lag while Chrome is running.
                        try:
                            from playwright.sync_api import sync_playwright
                            with sync_playwright() as p:
                                browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=1500)
                                if browser.contexts:
                                    cookies = browser.contexts[0].cookies(["https://www.linkedin.com"])
                                    logged_in = any(
                                        c.get("name") == "li_at" and len(c.get("value", "")) > 10
                                        for c in cookies
                                    )
                        except Exception:
                            # Keep browser_open separate from authentication:
                            # an open window alone is not proof of a login.
                            pass
                    self._json({"logged_in": logged_in, "browser_open": browser_open})

                elif path == "/api/hunt/logs":
                    self._json({
                        "is_running": _hunt_state["is_running"],
                        "logs": _hunt_logs[-80:],
                        "jobs": [j.to_dict() for j in _live_found_jobs],
                    })

                elif path == "/api/resume/download":
                    job_id = params.get("job_id", [None])[0]
                    file_format = params.get("format", ["pdf"])[0].lower()
                    jobs = storage.list_jobs()
                    target_job = next((j.job for j in jobs if j.job.id == job_id), None)
                    if not target_job and jobs:
                        target_job = jobs[0].job

                    if target_job:
                        tailored_data = tailor.tailor(profile, target_job)
                        if file_format == "tex":
                            tex_path = pdf_gen.generate_tex(profile, target_job, tailored_data)
                            self.send_response(200)
                            self.send_header("Content-Type", "text/x-tex; charset=utf-8")
                            self.send_header("Content-Disposition", f'attachment; filename="{tex_path.name}"')
                            self._send_cors_headers()
                            self.end_headers()
                            self.wfile.write(tex_path.read_bytes())
                            return
                        else:
                            pdf_path = pdf_gen.generate(profile, target_job, tailored_data)
                            self.send_response(200)
                            self.send_header("Content-Type", "application/pdf")
                            self.send_header("Content-Disposition", f'attachment; filename="{pdf_path.name}"')
                            self._send_cors_headers()
                            self.end_headers()
                            self.wfile.write(pdf_path.read_bytes())
                            return

                    self.send_response(404)
                    self._send_cors_headers()
                    self.end_headers()

                else:
                    self.send_response(404)
                    self._send_cors_headers()
                    self.end_headers()

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                if path == "/api/hunt/stop":
                    if _hunt_state["is_running"]:
                        _hunt_cancel_event.set()
                        add_hunt_log("⏹️ Durdurma isteği alındı; mevcut adım bitince arama duracak.")
                        self._json({"success": True, "message": "Durdurma istendi."})
                    else:
                        self._json({"success": False, "message": "Çalışan arama yok."}, status=409)
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                data = json.loads(raw_body) if raw_body else {}

                if path == "/api/jobs/status":
                    job_id = data.get("id")
                    new_status = data.get("status")
                    if job_id and new_status:
                        storage.update_status(job_id, new_status)
                        self._json({"success": True})
                        return

                elif path == "/api/sequences/approve":
                    step_id = data.get("step_id")
                    if step_id:
                        sequencer.approve_step(step_id)
                        self._json({"success": True})
                        return

                elif path == "/api/sequences/update":
                    step_id = data.get("step_id")
                    status = data.get("status")
                    if step_id and status:
                        storage.update_outreach_step(step_id, status=status)
                        self._json({"success": True})
                        return

                elif path == "/api/culture/analyze":
                    job_id = data.get("job_id")
                    company = data.get("company", "Tech Company")
                    job = storage.get_job_by_id(job_id).job if job_id and storage.get_job_by_id(job_id) else None
                    report = culture_agent.analyze_company(company, job)
                    self._json(report.to_dict())
                    return

                elif path == "/api/email-triage/mock":
                    mock_emails = [
                        {
                            "id": "mock_interview_1",
                            "sender": "talent@example.invalid",
                            "subject": "Interview Invitation: Senior Software Engineer at Example Co",
                            "body": (
                                "Hi there,\n\n"
                                "Thank you for applying to the Senior Software Engineer role at Example Co! "
                                "We were very impressed by your background in distributed architectures. "
                                "We would love to invite you to a 45-minute technical conversation with our Engineering Lead. "
                                "Please pick a convenient time on our Calendly: https://example.invalid/calendar\n\n"
                                "Best regards,\nTalent Team"
                            ),
                        }
                    ]
                    events = email_watcher.process_mock_inbox(mock_emails)
                    self._json([e.to_dict() for e in events])
                    return

                elif path == "/api/batch-apply":
                    limit = int(data.get("limit", 3))
                    headful = bool(data.get("headful", False))
                    result = batch_orchestrator.execute_batch_apply(
                        profile=profile,
                        limit=limit,
                        headful=headful,
                    )
                    self._json({
                        "prepared_count": sum(1 for item in result.results if item.get("status") == "prepared_for_review"),
                        "failed_count": result.failed_count,
                        "total": result.total_requested,
                    })
                    return

                elif path == "/api/profile":
                    for k, v in data.items():
                        if hasattr(profile, k):
                            setattr(profile, k, v)
                    try:
                        p_path = Path(__file__).parent / "sample_profile.json"
                        p_path.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                    except Exception as e:
                        logger.warning(f"Could not persist profile: {e}")

                    self._json({"success": True})
                    return

                elif path == "/api/profile/compile-tex":
                    raw_tex = data.get("tex", "")
                    tex_file = Path("candidate/base_cv.tex")
                    if raw_tex:
                        tex_file.parent.mkdir(parents=True, exist_ok=True)
                        tex_file.write_text(raw_tex, encoding="utf-8")
                    import subprocess
                    import shutil
                    tectonic_bin = "/opt/homebrew/bin/tectonic"
                    if not Path(tectonic_bin).exists():
                        tectonic_bin = shutil.which("tectonic") or "tectonic"
                    res = subprocess.run(
                        [tectonic_bin, str(tex_file), "--outdir", "candidate"],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if res.returncode == 0:
                        self._json({"success": True, "message": "Derleme başarılı"})
                    else:
                        self._json({"success": False, "error": res.stderr or "Tectonic derleme hatası"})
                    return

                elif path == "/api/tailor":
                    job_id = data.get("job_id")
                    jobs = storage.list_jobs()
                    target_job = next((j.job for j in jobs if j.job.id == job_id), None)
                    if target_job:
                        result = tailor.tailor(profile, target_job)
                        self._json(result)
                        return

                elif path == "/api/interview-prep":
                    job_id = data.get("job_id")
                    jobs = storage.list_jobs()
                    target_job = next((j.job for j in jobs if j.job.id == job_id), None)
                    if target_job:
                        prep_kit = prep_assistant.generate_prep_kit(profile, target_job)
                        self._json(prep_kit)
                        return

                elif path == "/api/hunt/login":
                    from job_hunter.navigator import BrowserNavigator
                    nav = BrowserNavigator(laya_client, headless=False)
                    def run_login_window():
                        try:
                            nav.open_interactive_login()
                        except Exception as e:
                            logger.exception("LinkedIn login window failed")
                            add_hunt_log(f"❌ LinkedIn giriş penceresi açılamadı: {e}")

                    threading.Thread(target=run_login_window, daemon=True).start()
                    self._json({
                        "success": True,
                        "message": "LinkedIn giriş penceresi açıldı. Giriş yaptıktan sonra pencereyi kapatabilirsiniz.",
                    })
                    return

                elif path == "/api/clear-all":
                    with storage._get_conn() as conn:
                        conn.execute("DELETE FROM jobs;")
                        conn.execute("DELETE FROM email_events;")
                        conn.execute("DELETE FROM outreach_steps;")
                    _live_found_jobs.clear()
                    _hunt_logs.clear()
                    _hunt_cancel_event.clear()
                    _hunt_state["is_running"] = True
                    _hunt_state["last_message"] = "Tarama başlatılıyor..."
                    add_hunt_log("🧹 Tüm kayıtlı ilan hafızası ve veritabanı sıfırlandı.")
                    self._json({"success": True})
                    return

                elif path == "/api/hunt":
                    if _hunt_state["is_running"]:
                        self._json({"success": False, "message": "Bir arama zaten çalışıyor."}, status=409)
                        return

                    url = data.get("url", "https://www.linkedin.com/jobs/search?keywords=Python+Backend&location=Turkey")
                    max_jobs = int(data.get("max_jobs", 5))
                    headful = bool(data.get("headful", False))

                    orchestrator = JobHunterOrchestrator(laya_client=laya_client, storage=storage)

                    _live_found_jobs.clear()
                    _hunt_logs.clear()
                    _hunt_cancel_event.clear()
                    # Set this before launching the background worker. The UI
                    # starts polling as soon as this request returns; leaving
                    # it false makes the first poll stop immediately and show
                    # "Tamamlandı" while the browser hunt is still running.
                    _hunt_state["is_running"] = True
                    _hunt_state["last_message"] = "Tarama başlatıldı..."
                    add_hunt_log(f"🚀 Otonom tarayıcı avı başlatıldı.")
                    add_hunt_log(f"🎯 Hedef URL: {url}")
                    add_hunt_log(f"⚙️ Tarayıcı modu: {'Görünür / Headful' if headful else 'Headless'}")

                    def run_hunt_worker():
                        _hunt_state["last_message"] = "Tarama başlatıldı..."
                        try:
                            def on_job_found(scored: ScoredJob):
                                _live_found_jobs.append(scored)
                                DesktopNotifier.notify_job_match(scored, min_score_threshold=0.70)

                            summary = orchestrator.hunt_from_browser(
                                start_url=url,
                                profile=profile,
                                max_jobs=max_jobs,
                                headless=not headful,
                                user_data_dir=DEFAULT_CHROME_PROFILE_DIR,
                                on_progress=on_job_found,
                                on_log=add_hunt_log,
                                should_stop=_hunt_cancel_event.is_set,
                            )
                            _hunt_state["discovered"] = summary.discovered
                            _hunt_state["shortlisted"] = summary.shortlisted
                            if _hunt_cancel_event.is_set():
                                _hunt_state["last_message"] = f"Durduruldu ({summary.discovered} ilan bulundu)"
                            else:
                                _hunt_state["last_message"] = f"Tamamlandı ({summary.discovered} ilan)"
                                add_hunt_log(f"🏁 Av tamamlandı. Toplam {summary.discovered} ilan incelendi.")
                        except Exception as e:
                            _hunt_state["last_message"] = f"Hata: {e}"
                            add_hunt_log(f"❌ Avlama hatası: {e}")
                        finally:
                            _hunt_state["is_running"] = False

                    threading.Thread(target=run_hunt_worker, daemon=True).start()

                    self._json({
                        "success": True,
                        "message": "Av arka planda başlatıldı! Canlı logları ve kartları izleyebilirsiniz.",
                    })
                    return

                self.send_response(400)
                self._send_cors_headers()
                self.end_headers()

            def log_message(self, format, *args):
                pass

        class ReusableThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            allow_reuse_address = True
            daemon_threads = True

        logger.info(f"Starting Job Hunter Level 3 Control Center at http://localhost:{self.port}")
        httpd = None
        try:
            httpd = ReusableThreadingServer(("", self.port), Handler)
            print(f"\n[+] Job Hunter Dashboard başarıyla yayında: http://localhost:{self.port}")
            print("    (Durdurmak için Ctrl+C tuşlayın - port anında serbest bırakılacaktır)\n")
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Dashboard kapatılıyor...")
        except OSError as e:
            if e.errno == 48:
                print(f"\n[!] HATA: Port {self.port} başka bir süreç tarafından kullanılıyor!")
                print(f"    İpucu: Docker veya başka bir servis portu tutuyor olabilir.")
                print(f"    Farklı bir portla çalıştırmak için: python3 -m job_hunter serve --port 8050\n")
            raise
        finally:
            if httpd:
                try:
                    httpd.shutdown()
                except Exception:
                    pass
                try:
                    httpd.server_close()
                except Exception:
                    pass
            print(f"[+] Port {self.port} tamamen kapatıldı ve serbest bırakıldı.\n")
