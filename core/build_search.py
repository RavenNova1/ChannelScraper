# -*- coding: utf-8 -*-
"""Build the search page from the machine transcript written by pipeline.py.

    python build_search.py [--in FILE] [--out FILE] [--compress]

The machine file is:

    @<videoId>\t<title>\t<durationSeconds>
    <startSecond>\t<words separated by spaces>\t<second-in-line per word>

The generated page needs no internet, no server and no libraries: it embeds the
whole corpus (optionally gzipped) as JSON.
"""

import argparse
import gzip
import json
import os
import re
import struct
import sys
from collections import Counter

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CORE_DIR) if os.path.basename(CORE_DIR) == "core" else CORE_DIR


def read_machine(path):
    videos = []
    lines = []
    index = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if not raw:
                continue
            if raw[0] == "@":
                parts = raw[1:].split("\t")
                vid = parts[0]
                title = parts[1] if len(parts) > 1 else vid
                try:
                    dur = int(parts[2]) if len(parts) > 2 else 0
                except ValueError:
                    dur = 0
                index[vid] = len(videos)
                videos.append([vid, title, dur])
                continue
            parts = raw.split("\t")
            if len(parts) < 2 or not parts[0].isdigit():
                continue
            start = int(parts[0])
            text = parts[1]
            offs = parts[2] if len(parts) > 2 else ""
            lines.append([start, len(videos) - 1, text, offs])
    return videos, lines


TEMPLATE = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--h:175;--fs:16px;--rdfs:20px;--ff:"Segoe UI","Noto Sans Arabic",Tajawal,Tahoma,Arial,sans-serif;
--bg:#f2f6f6;--card:#fff;--ink:#1f2d34;--dim:#64747d;--line:#e2e9eb;--acc:hsl(var(--h) 40% 32%);--soft:hsl(var(--h) 28% 95%);
--mark:#fbe6a2;--markt:#4a3800;--markb:#dcd2f7;--markbt:#2f1a63;--markc:#cde9d6;--markct:#15422a;--markd:#f6d2cf;--markdt:#5b1d18;
--red:#cf4a43;--ok:#237f5c;--shadow:0 8px 28px rgba(31,45,52,.07)}
.dark{--bg:#111b21;--card:#18252c;--ink:#e3ebee;--dim:#97a7b0;--line:#27383f;--acc:hsl(var(--h) 42% 70%);--soft:hsl(var(--h) 20% 20%);
--mark:#6b5416;--markt:#f7ebc4;--markb:#52407d;--markbt:#efe9ff;--markc:#2c5a40;--markct:#d8f1e2;--markd:#7a3b37;--markdt:#ffe3e0;
--ok:#5fcf9f;--shadow:0 8px 28px rgba(0,0,0,.35)}
body.naskh{--ff:"Noto Naskh Arabic","Traditional Arabic",Amiri,serif}
*{box-sizing:border-box}[hidden]{display:none!important}
html,body{margin:0;background:var(--bg);color:var(--ink);font:var(--fs)/1.7 var(--ff)}
button,input,select{font:inherit;color:inherit}button{cursor:pointer;border:0;background:none}
:focus-visible{outline:3px solid var(--acc);outline-offset:2px}
body.noscroll{overflow:hidden}
body.calm *,body.calm *::before{animation:none!important;transition:none!important}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
.wrap,main{max-width:860px;margin:0 auto;padding:0 16px}
.top{padding:26px 0 8px}
.hrow{display:flex;gap:12px;align-items:center;justify-content:space-between}
h1{margin:0;font-size:1.35em;font-weight:600;line-height:1.4}
#sub{margin:2px 0 16px;color:var(--dim)}
.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:18px;box-shadow:var(--shadow)}
.seg{display:flex;gap:4px;padding:4px;background:var(--soft);border-radius:14px;margin-bottom:14px}
.seg button{flex:1;padding:10px 8px;border-radius:11px;font-weight:600;color:var(--dim)}
.seg button.on{background:var(--card);color:var(--acc);box-shadow:0 1px 4px rgba(0,0,0,.1)}
.fields{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}
.fld{flex:1 1 150px;min-width:0}
.fld label{display:block;font-size:.85em;color:var(--dim);margin-bottom:4px}
.and{align-self:flex-end;height:54px;line-height:54px;color:var(--dim);font-weight:700}
input[type=text]{width:100%;height:54px;padding:0 16px;border:1.5px solid var(--line);border-radius:14px;background:var(--card);font-size:1.15em}
input[type=text]:focus{outline:0;border-color:var(--acc);box-shadow:0 0 0 4px hsl(var(--h) 45% 50%/.14)}
.go{height:54px;padding:0 32px;border-radius:14px;background:var(--acc);color:var(--card);font-weight:700;font-size:1.1em}
.dark .go,.dark .chip.on,.dark .basket #bhtml{color:#0b1419}
.pair{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:14px;padding-top:14px;border-top:1px dashed var(--line)}
.pair .lbl{color:var(--dim);font-size:.92em}
.chip{padding:8px 14px;border:1px solid var(--line);border-radius:99px;background:var(--bg);font-size:.92em}
.chip.on{background:var(--acc);border-color:var(--acc);color:var(--card)}
input[type=number]{width:84px;height:40px;padding:0 8px;border:1.5px solid var(--line);border-radius:10px;background:var(--card);font-size:1em;text-align:center}input[type=number]:focus{outline:0;border-color:var(--acc)}
.chk{display:flex;gap:6px;align-items:center;margin-inline-start:auto;font-size:.92em}
.hint{flex-basis:100%;margin:2px 0 0;color:var(--dim);font-size:.92em}.hint b{color:var(--ink)}
main{padding-top:18px;padding-bottom:120px}
.srow{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;min-height:26px;margin-bottom:10px}#status{color:var(--dim)}#status b{color:var(--ink)}
.lg{margin-inline-start:10px}.lg mark{margin-inline-start:6px;padding:1px 10px;border-radius:99px}
#tools{display:flex;gap:6px}#tools .sm{padding:2px 10px;font-size:.76em}
.sm{padding:7px 14px;border:1px solid var(--line);border-radius:99px;background:var(--card);font-size:.88em;color:var(--dim)}
.sm:hover{color:var(--acc);border-color:var(--acc)}
.err{color:#c4302b}.dark .err{color:#ff8f8f}
#intro{text-align:center;padding:26px 4px;color:var(--dim)}#intro h2{margin:0 0 6px;color:var(--ink)}
.steps{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin:18px 0}
.steps div{flex:1 1 200px;max-width:250px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px}
.steps b{display:block;color:var(--acc);font-size:1.3em}
.vid{background:var(--card);border:1px solid var(--line);border-radius:20px;margin-bottom:14px;overflow:hidden}
.vh{display:flex;width:100%;gap:12px;align-items:center;padding:15px 18px;text-align:start;background:var(--soft)}
.vh .t{flex:1;font-weight:600;line-height:1.5}
.vh .c{font-size:.82em;white-space:nowrap;background:var(--card);color:var(--acc);border:1px solid var(--line);border-radius:99px;padding:3px 12px}
.chev{display:inline-block;color:var(--acc);transition:transform .25s}.closed .chev{transform:rotate(90deg)}
.vb{display:grid;grid-template-rows:1fr;transition:grid-template-rows .2s ease,visibility .2s}
.closed .vb{grid-template-rows:0fr;visibility:hidden}
.vbi{overflow:hidden;min-height:0}
.hit{display:flex;gap:14px;padding:16px 18px;border-top:1px solid var(--line);cursor:pointer;content-visibility:auto;contain-intrinsic-size:auto 130px}
.hit:hover{background:var(--soft)}
.time{flex:none;align-self:flex-start;min-width:60px;text-align:center;font:700 .85em/1 Consolas,monospace;direction:ltr;color:var(--acc);background:var(--soft);padding:7px 10px;border-radius:9px;text-decoration:none}
.body{flex:1;min-width:0}.snip{line-height:2;word-wrap:break-word}
mark{background:var(--mark);color:var(--markt);border-radius:4px;padding:1px 3px}mark.b{background:var(--markb);color:var(--markbt)}
.moreb{margin-inline-start:6px;padding:2px 10px;border-radius:8px;color:var(--acc);font-weight:700}
.moreb:hover{background:var(--soft);text-decoration:underline}
.acts{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.acts a,.acts button{padding:7px 14px;border:1px solid var(--line);border-radius:99px;font-size:.84em;text-decoration:none;color:var(--dim)}
.acts button:hover{color:var(--acc);border-color:var(--acc)}
.acts .ytb{background:var(--red);border-color:var(--red);color:#fff;font-weight:600}
.add.picked{color:var(--ok)!important;border-color:var(--ok)!important}
#more{display:block;margin:12px auto;padding:12px 28px;border:1px solid var(--line);border-radius:99px;background:var(--card);color:var(--acc);font-weight:600}
@media(max-width:560px){.hit{flex-direction:column;gap:8px}.go{width:100%}}
.rd{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:16px}
.rd-back{position:absolute;inset:0;background:rgba(8,16,22,.68);animation:fi .25s}
.rd-card{position:relative;width:min(780px,100%);max-height:min(88vh,860px);display:flex;flex-direction:column;overflow:hidden;background:var(--card);border-radius:24px;
box-shadow:0 30px 80px rgba(0,0,0,.45),0 0 0 1px var(--line),0 0 0 6px hsl(var(--h) 45% 50%/.12)}
.rd-head{display:flex;gap:12px;align-items:flex-start;padding:18px 22px 14px;background:var(--soft);border-bottom:1px solid var(--line)}
.rd-head>div{flex:1;min-width:0}#rdTitle{font-weight:700;line-height:1.5}#rdMeta{color:var(--dim);font-size:.88em}
.x{width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--card)}
#rdBody{position:relative;flex:1;overflow:auto;overscroll-behavior:contain;contain:layout style;padding:8px 22px 18px;font-size:var(--rdfs);line-height:2.1}
.min{padding:14px 0;border-bottom:1px dashed var(--line)}.min p{margin:0}.min:not(.cur) p{color:var(--dim)}
.mt{display:inline-block;margin-bottom:4px;padding:5px 9px;border-radius:8px;background:var(--soft);color:var(--acc);font:700 .62em/1 Consolas,monospace;direction:ltr;text-decoration:none}
mark.f{animation:pulse 1.2s .4s 1}
.rdm{display:block;width:100%;margin:8px 0;padding:10px;border:1px dashed var(--line);border-radius:12px;color:var(--acc);font-size:.8em}
.rd-foot{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;padding:12px 18px;border-top:1px solid var(--line)}
.rd-foot .g{display:flex;gap:8px;flex-wrap:wrap}
.rd-foot button,.rd-foot a{padding:9px 16px;border:1px solid var(--line);border-radius:99px;font-size:.9em;text-decoration:none;color:var(--ink)}
.rd-foot .ytb{background:var(--red);border-color:var(--red);color:#fff}.rd-foot button:disabled{opacity:.35}
@keyframes fi{from{opacity:0}}@keyframes pulse{50%{box-shadow:0 0 0 8px hsla(45,100%,60%,.55)}}
@media(max-width:600px){.rd{padding:0;align-items:end}.rd-card{max-height:94vh;border-radius:22px 22px 0 0}}
#sback{position:fixed;inset:0;z-index:65;background:rgba(8,16,22,.45)}
.sheet{position:fixed;inset-block:0;inset-inline-start:0;z-index:70;width:min(400px,100%);overflow:auto;padding:18px 20px 30px;background:var(--card);box-shadow:var(--shadow);
transform:translateX(100%);visibility:hidden;transition:transform .3s,visibility .3s}
.sheet.on{transform:none;visibility:visible}
.shead{display:flex;justify-content:space-between;align-items:center;font-size:1.15em}
.sheet h3{margin:20px 0 0;color:var(--acc);font-size:1em}
.set{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}
.set small{display:block;color:var(--dim);font-size:.8em;line-height:1.5}
.sheet select,.sheet input[type=text]{height:40px;width:150px;padding:0 10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);font-size:1em}
.sw{appearance:none;flex:none;width:46px;height:26px;border-radius:99px;background:var(--line);position:relative;cursor:pointer;transition:background .2s}
.sw::after{content:"";position:absolute;top:3px;inset-inline-start:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:transform .2s}
.sw:checked{background:var(--acc)}.sw:checked::after{transform:translateX(-20px)}
#sreset{margin-top:18px}
.basket{position:fixed;inset:auto 0 0 0;z-index:40;display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:center;padding:10px 16px;background:var(--card);border-top:1px solid var(--line);box-shadow:0 -8px 24px rgba(0,0,0,.12)}
.basket b{color:var(--acc)}.basket button{padding:9px 16px;border:1px solid var(--line);border-radius:99px;font-size:.88em}
.basket #bhtml{background:var(--acc);border-color:var(--acc);color:var(--card);font-weight:700}.basket button:disabled{opacity:.4}
.drawer{position:fixed;inset-inline:0;z-index:39;display:none;background:var(--card);border-top:1px solid var(--line);box-shadow:0 -14px 34px rgba(0,0,0,.2)}
.drawer.on{display:block}.dwrap{max-width:860px;margin:0 auto;padding:12px 16px}
.dhead{display:flex;align-items:center;gap:10px;margin-bottom:8px}.dhead .x{margin-inline-start:auto;width:auto;padding:0 16px;height:36px;border-radius:99px}
#dlist{max-height:46vh;overflow:auto}
.ditem{display:flex;gap:10px;padding:10px;margin-bottom:6px;border:1px solid var(--line);border-radius:12px;background:var(--bg)}
.ditem .i{min-width:18px;text-align:center;color:var(--dim)}.ditem .dt{flex:1;min-width:0}.ditem .dh{font-weight:700;font-size:.92em}
.dm{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:4px}.ditem .time{padding:4px 8px;min-width:0}
.ds{font-size:.88em;color:var(--dim);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.rm{padding:3px 12px;border:1px solid var(--line);border-radius:99px;color:var(--red);font-size:.82em}
.dempty{text-align:center;color:var(--dim);padding:16px}
.toast{position:fixed;bottom:90px;left:50%;transform:translateX(-50%);z-index:90;padding:10px 20px;border-radius:99px;background:var(--ink);color:var(--card);opacity:0;pointer-events:none;transition:opacity .2s}.toast.on{opacity:1}
#splash{position:fixed;inset:0;z-index:100;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;text-align:center;padding:20px}
#splash .bar{width:min(360px,80vw);height:8px;background:var(--line);border-radius:4px;overflow:hidden}
#splash .bar i{display:block;height:100%;width:0;background:var(--acc);transition:width .25s}#splash .msg{color:var(--dim);font-size:.9em}
mark.c{background:var(--markc);color:var(--markct)}mark.d{background:var(--markd);color:var(--markdt)}
.hbtns{display:flex;gap:8px;align-items:center}.hwrap{position:relative}
.hpop{position:absolute;left:0;top:calc(100% + 8px);z-index:50;width:min(300px,86vw);max-height:50vh;overflow:auto;padding:8px;background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}
.hitem{display:flex;align-items:center;gap:4px}.hi{flex:1;min-width:0;padding:8px 10px;border-radius:10px;text-align:start;font-size:.9em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hi:hover{background:var(--soft);color:var(--acc)}.hx{padding:6px 9px;border-radius:8px;color:var(--dim);font-size:.8em}.hx:hover{color:var(--red)}
.hempty{padding:12px;text-align:center;color:var(--dim);font-size:.9em}#hclear{width:100%;margin-top:6px}
.rx{margin-inline-start:8px;padding:0;color:var(--red);font-size:.9em}
  .acts .delb {
    background: transparent;
    border: 1px solid var(--line);
    color: var(--dim);
    font-size: 11.5px;
    padding: 4px 8px;
    border-radius: 6px;
    cursor: pointer;
  }
  .acts .delb:hover {
    border-color: var(--red);
    color: var(--red);
    background: var(--red-bg);
  }

</style>
</head>
<body>
<div id="splash"><div>جاري تحميل التفريغ…</div><div class="bar"><i id="pbar"></i></div><div class="msg" id="pmsg">تهيئة</div></div>

<header class="top"><div class="wrap">
  <div class="hrow"><h1>__TITLE__</h1><div class="hbtns"><div class="hwrap"><button id="histBtn" class="sm" type="button" aria-haspopup="true">🕘 السجل</button>
    <div class="hpop" id="hpop" hidden><div id="hlist"></div><button id="hclear" class="sm" type="button">مسح السجل</button></div></div>
    <button id="settingsBtn" class="sm" type="button">⚙ الإعدادات</button></div></div>
  <p id="sub">__SUB__</p>
  <div class="card">
    <div class="seg" role="tablist" aria-label="طريقة البحث">
      <button id="m1" class="on" type="button" role="tab" aria-selected="true">كلمة أو جملة</button>
      <button id="m2" type="button" role="tab" aria-selected="false">كلمتان قريبتان من بعض</button>
    </div>
    <div class="fields">
      <div class="fld"><label id="lab1" for="q">اكتب كلمة أو جملة</label><input id="q" type="text" autocomplete="off" spellcheck="false"></div>
      <span class="and" data-n="2" hidden>و</span>
      <div class="fld" data-n="2" hidden><label for="q2">الكلمة الثانية</label><input id="q2" placeholder="مثال: الفتن" type="text" autocomplete="off" spellcheck="false"></div>
      <span class="and" data-n="3" hidden>و</span>
      <div class="fld" data-n="3" hidden><label for="q3">الكلمة الثالثة <button class="rx" type="button" data-r="3">إزالة</button></label><input id="q3" type="text" autocomplete="off" spellcheck="false"></div>
      <span class="and" data-n="4" hidden>و</span>
      <div class="fld" data-n="4" hidden><label for="q4">الكلمة الرابعة <button class="rx" type="button" data-r="4">إزالة</button></label><input id="q4" type="text" autocomplete="off" spellcheck="false"></div>
      <button id="go" class="go" type="button">بحث</button>
    </div>
    <div class="pair" id="pair" hidden>
      <span class="lbl">كم تبعد الكلمتان عن بعض؟</span>
      <label class="lbl">أقصى عدد كلمات بين كل كلمتين <input id="gap" type="number" min="0" max="300" value="100" inputmode="numeric"></label>
      <button id="addw" class="chip" type="button">＋ أضف كلمة ثالثة</button>
      <label class="chk"><input id="orderany" type="checkbox" checked> بأي ترتيب</label>
      <p class="hint" id="pxsum"></p>
    </div>
  </div>
</div></header>

<main>
  <div class="srow"><div id="status"></div>
  <div id="tools" hidden><button class="sm" id="foldNone" type="button">▸ طيّ الكل</button><button class="sm" id="foldAll" type="button">▾ فتح الكل</button></div></div>
  <div id="intro">
    <h2>كيف تبحث؟</h2>
    <div class="steps"><div><b>1</b>اكتب كلمة واضغط «بحث»</div><div><b>2</b>اضغط «… المزيد» لقراءة الكلام كاملًا</div><div><b>3</b>اضغط «يوتيوب» لتسمعه بنفسك</div></div>
    <div id="sampleChips">جرّب:
      <button class="chip" type="button" data-a="العلم">العلم</button>
      <button class="chip" type="button" data-a="العمل">العمل</button>
      <button class="chip" type="button" data-m="2" data-a="الحق" data-b="البيان">الحق + البيان (كلمتان معًا)</button></div>
  </div>
  <div id="results"></div>
  <button id="more" type="button" style="display:none">عرض المزيد</button>
</main>

<div id="sback" hidden></div>
<aside class="sheet" id="sheet" aria-label="الإعدادات">
  <div class="shead"><b>الإعدادات</b><button id="sclose" class="sm" type="button">تم</button></div>
  <h3>البحث</h3>
  <label class="set"><span>بحث مرن<small>يجد الكلمة حتى لو كُتبت بـ «ال» أو بحرف مختلف قليلًا</small></span><input id="loose" class="sw" type="checkbox" checked></label>
  <label class="set"><span>حصر البحث في فيديو<small>اكتب جزءًا من عنوانه</small></span><input id="vfilter" type="text" autocomplete="off"></label>
  <h3>النتائج</h3>
  <label class="set"><span>طول المقتطف</span><select id="ctx"><option value="60">قصير</option><option value="120">متوسط</option><option value="220" selected>طويل</option></select></label>
  <label class="set"><span>ترتيب الفيديوهات</span><select id="sort"><option value="video" selected>كما في القناة</option><option value="count">الأكثر نتائج أولًا</option></select></label>
  <label class="set"><span>الفيديوهات عند ظهور النتائج</span><select id="fold"><option value="all" selected>مفتوحة كلها</option><option value="first">أول ثلاثة مفتوحة</option><option value="none">مطويّة كلها</option></select></label>
  <h3>المظهر</h3>
  <div id="delBox" style="margin-top:14px; margin-bottom:16px; border-top:1px solid var(--line); padding-top:10px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <span style="font-size:13px; font-weight:600; color:var(--ink)">الكلمات المحذوفة من التفريغ (<span id="delCount">0</span>)</span>
      <button id="delRestoreAll" class="sm" type="button" onclick="restoreAllDeleted()" style="display:none; color:var(--acc); border:1px solid var(--line); padding:3px 8px; border-radius:5px; background:transparent; font-size:11.5px; cursor:pointer;">↺ استرجاع الكل</button>
    </div>
    <div id="delList" style="max-height:220px; overflow-y:auto; border:1px solid var(--line); border-radius:8px; padding:6px; background:var(--bg); font-size:12px;"></div>
  </div>

  <label class="set"><span>الشكل</span><select id="theme"><option value="light" selected>فاتح</option><option value="dark">داكن</option><option value="auto">حسب جهازك</option></select></label>
  <label class="set"><span>حجم الخط</span><select id="fs"><option value="14">صغير</option><option value="16" selected>عادي</option><option value="18">كبير</option><option value="21">كبير جدًا</option></select></label>
  <label class="set"><span>نوع الخط</span><select id="font"><option value="sans" selected>واضح</option><option value="naskh">خط الكتب</option></select></label>
  <label class="set"><span>اللون</span><select id="hue"><option value="175" selected>أخضر مزرق</option><option value="215">أزرق</option><option value="275">بنفسجي</option><option value="25">برتقالي</option></select></label>
  <label class="set"><span>تقليل الحركة<small>يوقف الانتقالات والتأثيرات</small></span><input id="motion" class="sw" type="checkbox"></label>
  <input id="rdfs" type="hidden" value="20">
  <button id="sreset" class="sm" type="button">استعادة الإعدادات الأصلية</button>
</aside>

<div class="rd" id="reader" hidden>
  <div class="rd-back" id="rdBack"></div>
  <article class="rd-card" role="dialog" aria-modal="true" aria-labelledby="rdTitle">
    <div class="rd-head"><div><div id="rdTitle"></div><div id="rdMeta"></div></div><button id="rdClose" class="x" type="button" aria-label="إغلاق">✕</button></div>
    <div id="rdBody"></div>
    <div class="rd-foot">
      <div class="g"><button id="rdPrev" type="button">→ السابقة</button><button id="rdNext" type="button">التالية ←</button></div>
      <div class="g"><button id="rdSmall" type="button" aria-label="تصغير الخط">أ-</button><button id="rdBig" type="button" aria-label="تكبير الخط">أ+</button>
        <button id="rdCopy" type="button">نسخ النص</button><button id="rdSave" class="add" type="button"></button>
        <a id="rdYt" class="ytb" target="_blank" rel="noopener">يوتيوب</a></div>
    </div>
  </article>
</div>

<div class="drawer" id="drawer"><div class="dwrap">
  <div class="dhead"><b>المحفوظات</b><span id="dcount"></span><button id="dclose" class="x" type="button">إغلاق</button></div>
  <div id="dlist"></div>
</div></div>
<div class="basket" hidden>
  <span id="bcount"></span>
  <button id="bhtml" type="button" disabled>تحميل كصفحة</button>
  <button id="blist" type="button" disabled>عرض المحفوظات</button>
  <button id="bcsv" type="button" disabled>ملف CSV</button>
  <button id="btxt" type="button" disabled>ملف نصي</button>
  <button id="bclear" type="button">مسح الكل</button>
</div>
<div class="toast" id="toast"></div>

<script id="corpus" type="application/json">__RAW__</script>
<script id="b85" type="text/plain">__B85__</script>
<script>
"use strict";
const CORPUS_EL = document.getElementById("corpus");
const RAWSRC = CORPUS_EL ? CORPUS_EL.textContent : "";
const B85_EL = document.getElementById("b85");
const B85SRC = B85_EL ? B85_EL.textContent : "";
const B85LEN = __B85LEN__;
const GZSRC = __GZ__;

const SAFE85 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%()*+-;=?@^_{|}~./:[";
const B85_MAP = new Int32Array(256).fill(-1);
for (let i = 0; i < SAFE85.length; i++) B85_MAP[SAFE85.charCodeAt(i)] = i;

function decodeB85(str, outLen) {
  const out = new Uint8Array(outLen);
  const n = str.length;
  let i = 0, o = 0;
  while (i < n) {
    const rem = n - i;
    if (rem >= 5) {
      const acc = ((((B85_MAP[str.charCodeAt(i)] * 85 +
                     B85_MAP[str.charCodeAt(i+1)]) * 85 +
                     B85_MAP[str.charCodeAt(i+2)]) * 85 +
                     B85_MAP[str.charCodeAt(i+3)]) * 85 +
                     B85_MAP[str.charCodeAt(i+4)]) >>> 0;
      out[o] = (acc >>> 24);
      out[o+1] = (acc >>> 16) & 255;
      out[o+2] = (acc >>> 8) & 255;
      out[o+3] = acc & 255;
      o += 4;
      i += 5;
    } else {
      let acc = 0;
      for (let k = 0; k < rem; k++) acc = acc * 85 + B85_MAP[str.charCodeAt(i + k)];
      for (let k = rem; k < 5; k++) acc = acc * 85 + 84;
      acc = (acc >>> 0);
      for (let k = 0; k < rem - 1; k++) {
        out[o++] = (acc >>> (24 - k * 8)) & 255;
      }
      i += rem;
    }
  }
  return out;
}

/* ---------- Arabic folding ---------- */
const TBL = new Array(65536);
(function () {
  for (let c = 0x0610; c <= 0x061A; c++) TBL[c] = null;      // harakat
  for (let c = 0x064B; c <= 0x065F; c++) TBL[c] = null;
  for (let c = 0x0670; c <= 0x0670; c++) TBL[c] = null;
  for (let c = 0x06D6; c <= 0x06ED; c++) TBL[c] = null;      // quran marks
  TBL[0x0640] = null;                                        // tatweel
  TBL[0x0622] = 0x0627; TBL[0x0623] = 0x0627; TBL[0x0625] = 0x0627;
  TBL[0x0671] = 0x0627; TBL[0x0672] = 0x0627; TBL[0x0673] = 0x0627;
  TBL[0x0629] = 0x0647; TBL[0x0649] = 0x064A;
  TBL[0x06CC] = 0x064A; TBL[0x06D2] = 0x064A; TBL[0x06D3] = 0x064A;
  TBL[0x0624] = 0x0648; TBL[0x06C6] = 0x0648; TBL[0x06C7] = 0x0648; TBL[0x06C8] = 0x0648;
  TBL[0x0626] = 0x064A; TBL[0x06C0] = 0x0647; TBL[0x06C1] = 0x0647; TBL[0x06C2] = 0x0647;
  TBL[0x06BE] = 0x0647; TBL[0x06C3] = 0x0647;
  TBL[0x064A] = 0x064A;
})();
function foldChar(c) {
  const v = TBL[c];
  if (v === null) return "";
  if (v !== undefined) return String.fromCharCode(v);
  return c === 0x20 || c === 0x09 || c === 0x0A ? " " : String.fromCharCode(c);
}
function fold(s) {
  const parts = [];
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0x0600 && c <= 0x06FF) { const r = foldChar(c); if (r) parts.push(r); }
    else if (c === 0x200C || c === 0x200D || c === 0x200E || c === 0x200F ||
             (c >= 0x202A && c <= 0x202E) || (c >= 0x2066 && c <= 0x2069) ||
             c === 0xFEFF || (c >= 0x064B && c <= 0x065F)) { /* skip */ }
    else parts.push(String.fromCharCode(c));
  }
  return parts.join("").replace(/\s+/g, " ").toLowerCase();
}
function foldWithMap(s) {
  let out = "";
  const map = new Array(s.length + 1);
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    let r;
    if (c >= 0x0600 && c <= 0x06FF) r = foldChar(c);
    else if (c === 0x200C || c === 0x200D || c === 0x200E || c === 0x200F ||
             (c >= 0x202A && c <= 0x202E) || (c >= 0x2066 && c <= 0x2069) ||
             c === 0xFEFF) r = "";
    else r = String.fromCharCode(c).toLowerCase();
    if (r === " " || r === "\n" || r === "\t") {
      if (out.length && out[out.length - 1] === " ") { map[i] = out.length; continue; }
      r = " ";
    }
    for (let k = 0; k < r.length; k++) { map[i] = out.length; out += r[k]; }
  }
  map[s.length] = out.length;
  return { text: out, map: map };
}
function stem(w) {
  if (w.length > 4 && w.startsWith("ال") && w.length - 2 >= 3) return w.slice(2);
  return w;
}
function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

/* ---------- data ---------- */
let VIDS = [];      // [id, title, duration]
let LT = [];        // line text
let LS = [];        // line start second
let LV = [];        // video index
let LO = [];        // per-word second inside the line

let FT = [];        // folded copy of each line, used only for matching (same length as LT)
const JUNK = /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640\u200C-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/;
const JUNKG = new RegExp(JUNK.source, "g");
const LETTERS = /[آأإٱٲٳةۀہۂۃھىیےۓؤۆۇۈئA-Z]/;
function letterFold(t) {
  return t.replace(/[آأإٱٲٳ]/g, "ا").replace(/[ةۀہۂۃھ]/g, "ه").replace(/[ىیےۓ]/g, "ي")
          .replace(/[ؤۆۇۈ]/g, "و").replace(/ئ/g, "ي").toLowerCase();
}
function parseJson(D) {
  VIDS = D.v;
  if (D.l) {
    const n = D.l.length;
    LT = new Array(n); FT = new Array(n); LS = new Array(n); LV = new Array(n); LO = new Array(n);
    for (let i = 0; i < n; i++) {
      const row = D.l[i];
      let t = row[2];
      if (JUNK.test(t)) t = t.replace(JUNKG, "");
      LS[i] = row[0]; LV[i] = row[1]; LT[i] = t; LO[i] = row[3];
      FT[i] = LETTERS.test(t) ? letterFold(t) : t;
    }
    ORIG_LT = LT.slice();
    D.l = null;
    return;
  }
  const n = D.t ? D.t.length : 0;
  LT = D.t; LS = D.s; LO = D.o; LV = new Int32Array(n); FT = new Array(n);
  let vi = 0, nextCut = VIDS[0][3];
  for (let i = 0; i < n; i++) {
    while (i >= nextCut) { vi++; nextCut += VIDS[vi][3]; }
    LV[i] = vi;
    let t = LT[i];
    if (JUNK.test(t)) { t = t.replace(JUNKG, ""); LT[i] = t; }
    FT[i] = LETTERS.test(t) ? letterFold(t) : t;
  }
  ORIG_LT = LT.slice();
  D.t = null; D.s = null; D.o = null;
}

function parseAll(input) {
  if (typeof input === "string") {
    parseJson(JSON.parse(input));
    return;
  }

  const buf = input;
  const u8 = new Uint8Array(buf);
  if (u8[0] === 123) {
    parseJson(JSON.parse(new TextDecoder("utf-8").decode(buf)));
    return;
  }

  const view = new DataView(buf);
  const jsonLen = view.getUint32(0);
  const jsonBytes = new Uint8Array(buf, 4, jsonLen);
  const meta = JSON.parse(new TextDecoder("utf-8").decode(jsonBytes));
  const varintBuf = new Uint8Array(buf, 4 + jsonLen);

  VIDS = meta.v;
  LS = meta.s;
  LO = meta.o;
  const wordCounts = meta.w;
  const dict = meta.d.split("\n");
  const n = wordCounts.length;

  LT = new Array(n);
  FT = new Array(n);
  LV = new Int32Array(n);

  let vi = 0, nextCut = VIDS[0][3];
  let ptr = 0;
  for (let i = 0; i < n; i++) {
    while (i >= nextCut) {
      vi++;
      nextCut += VIDS[vi][3];
    }
    LV[i] = vi;
    const wc = wordCounts[i];
    const parts = new Array(wc);
    for (let j = 0; j < wc; j++) {
      let val = 0, shift = 0;
      while (true) {
        const b = varintBuf[ptr++];
        val |= (b & 127) << shift;
        if (!(b & 128)) break;
        shift += 7;
      }
      parts[j] = dict[val];
    }
    const t = parts.join(" ");
    LT[i] = t;
    FT[i] = LETTERS.test(t) ? letterFold(t) : t;
  }
  ORIG_LT = LT.slice();
  try { initChips(dict); } catch (e) {}
  meta.d = null; meta.w = null;
}

function bindChips() {
  document.querySelectorAll("#intro [data-a]").forEach(function (b) {
    b.onclick = function () {
      NW = 2; $("q3").value = $("q4").value = "";
      setMode(b.dataset.m === "2" ? 2 : 1);
      $("q").value = b.dataset.a; $("q2").value = b.dataset.b || "";
      proxSum(); search();
    };
  });
}

function initChips(dict) {
  if (!dict || dict.length < 5) return;
  const stopWords = new Set(["في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك", "التي", "الذي", "الذين", "ما", "لا", "أن", "إن", "هو", "هي", "ثم", "أو", "كل", "كان", "كانت", "يكون", "تكون", "له", "لها", "لهم", "به", "بها", "بهم", "فيه", "فيها", "فيهم", "عنه", "عنها", "عنهم", "منه", "منها", "منهم"]);
  const picks = [];
  for (let w of dict) {
    if (w.length >= 4 && !stopWords.has(w) && !/[a-zA-Z0-9]/.test(w)) {
      picks.push(w);
      if (picks.length >= 2) break;
    }
  }
  if (picks.length >= 2) {
    const el = document.getElementById("sampleChips");
    if (el) {
      el.innerHTML = "جرّب: " +
        picks.map(w => `<button class="chip" type="button" data-a="${escapeHtml(w)}">${escapeHtml(w)}</button>`).join(" ") +
        ` <button class="chip" type="button" data-m="2" data-a="${escapeHtml(picks[0])}" data-b="${escapeHtml(picks[1])}">${escapeHtml(picks[0])} + ${escapeHtml(picks[1])} (كلمتان معًا)</button>`;
      bindChips();
    }
  }
}

function hms(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m)) + ":" + String(s).padStart(2, "0");
}
function watchUrl(vid, sec) {
  return "https://www.youtube.com/watch?v=" + vid + "&t=" + sec + "s";
}
function videoUrl(vid) { return "https://www.youtube.com/watch?v=" + vid; }

/* ---------- query handling ---------- */
const AFFIX = "(?:[وفبكل]{0,2}(?:ال)?)?";
const SUFFIX = "(?:ه|ها|هم|هما|كم|كما|نا|ين|ون|ات|ي|و|ت)?";
function buildRegex(q, loose) {
  const parts = fold(q).trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return null;
  if (!loose) {
    return new RegExp("(?<![\\u0621-\\u064A])" + parts.map(escapeRe).join("\\s+") + "(?![\\u0621-\\u064A])", "g");
  }
  let body = "";
  parts.forEach(function (w, i) {
    let part = AFFIX + escapeRe(stem(w));
    if (i === parts.length - 1) part += SUFFIX;
    body += (i ? "\\s+" : "") + part;
  });
  return new RegExp("(?<![\\u0621-\\u064A])" + body + "(?![\\u0621-\\u064A])", "g");
}

/* word index of a character offset inside a line */
function wordIndexAt(text, pos) {
  let idx = 0;
  for (let i = 0; i < pos && i < text.length; i++) if (text.charCodeAt(i) === 32) idx++;
  return idx;
}
function secondOf(lineIndex, pos) {
  const offs = LO[lineIndex];
  if (!offs) return LS[lineIndex];
  const k = wordIndexAt(LT[lineIndex], pos);
  if (offs.indexOf(" ") < 0) {
    return LS[lineIndex] + (k < offs.length ? offs.charCodeAt(k) - 35 : 0);
  }
  let acc = 0, start = 0, i = 0;
  const n = offs.length;
  while (i < n) {
    let j = i;
    while (j < n && offs.charCodeAt(j) !== 32) j++;
    if (acc === k) return LS[lineIndex] + (parseInt(offs.slice(i, j), 10) || 0);
    acc++;
    i = j + 1;
  }
  return LS[lineIndex];
}

/* ---------- search ---------- */
const PAGE = 40;
const MAXHITS = 30000;
let ALL = [], SHOWN = 0, LASTVID = -1, LASTBOX = null, COUNTS = new Map();
const STAT = { ms: 0, q: "", capped: false };

function currentSettings() {
  return {
    loose: document.getElementById("loose").checked,
    ctx: parseInt(document.getElementById("ctx").value, 10) || 120,
    vf: document.getElementById("vfilter").value.trim()
  };
}

function resetList() {
  ALL = []; SHOWN = 0; STAT.ms = 0; STAT.capped = false;
  LASTBOX = null; LASTVID = -1;
  $("results").innerHTML = "";
  $("more").style.display = "none";
  $("tools").hidden = true;
  $("intro").hidden = true;
}

function search() {
  const q1 = $("q").value.trim();
  const extra = MODE === 2 ? ["q2", "q3", "q4"].slice(0, NW - 1).map(function (id) { return $(id).value.trim(); }) : [];
  const gap = Math.max(0, Math.min(300, parseInt($("gap").value, 10) || 0));
  resetList();
  const st = $("status");
  const short = function (w) { return fold(w).replace(/\s+/g, "").length < 2; };
  if (short(q1)) { st.innerHTML = '<span class="err">اكتب حرفين على الأقل.</span>'; return; }
  if (extra.some(short)) {
    st.innerHTML = '<span class="err">اكتب كل الكلمات الظاهرة (حرفان على الأقل لكل كلمة)، أو اضغط «إزالة» للكلمة الزائدة.</span>';
    return;
  }
  const words = [q1].concat(extra);
  STAT.q = words.join("  ⟷  ");
  const t0 = performance.now();
  if (extra.length) searchProximity(words, gap); else searchSingle(q1);
  STAT.ms = Math.round(performance.now() - t0);
  STAT.capped = ALL.length >= MAXHITS;
  if (!ALL.length) {
    let more = "";
    if (/[\u0621-\u064A]/.test(q1)) {
      more = currentSettings().loose
        ? " جرّب كلمة أقصر، أو ارفع «أقصى عدد كلمات» في البحث بالتقارب."
        : " جرّب تفعيل <b>البحث المرن</b> من الإعدادات ⚙.";
    }
    st.innerHTML = "<b>لا نتائج</b> لـ «" + escapeHtml(words.join(" + ")) + "»." + more +
      " التفريغ آلي، فقد تكون الكلمة مكتوبة بشكل مختلف.";
    updateMore();
    return;
  }
  histAdd(words, gap, $("orderany").checked);
  renderAll();
}

function searchSingle(q) {
  const s = currentSettings();
  const re = buildRegex(q, s.loose);
  if (!re) return;
  QRE = { res: [re] };
  for (let i = 0, n = LT.length; i < n; i++) {
    if (s.vf && VIDS[LV[i]][1].indexOf(s.vf) < 0) continue;
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(FT[i])) !== null) {
      if (!m[0].length) { re.lastIndex++; continue; }
      ALL.push({ line: i, start: m.index, len: m[0].length, sec: null });
      if (ALL.length >= MAXHITS) return;
    }
  }
}

/* 2 to 4 words; each word at most `gap` words after the one before it.
   Every line is looked at together with the line before it (same video), so
   words that straddle a minute boundary are found too. */
function wordCount(t) { let c = 1; for (let i = 0; i < t.length; i++) if (t.charCodeAt(i) === 32) c++; return c; }
function mkItem(t, l, m, text, off) {
  let n = 1;
  for (let i = m[0]; i < m[1]; i++) if (text.charCodeAt(i) === 32) n++;
  return { t: t, l: l, s: m[0], e: m[1], w: off + wordIndexAt(text, m[0]), n: n };
}
function searchProximity(qs, gap) {
  const s = currentSettings();
  const res = qs.map(function (q) { return buildRegex(q, s.loose); });
  if (res.some(function (r) { return !r; })) return;
  QRE = { res: res };
  const N = res.length, anyOrder = $("orderany").checked;
  let prevM = null, prevLine = -1, prevVid = -1;
  for (let i = 0, n = LT.length; i < n; i++) {
    const vi = LV[i];
    if (s.vf && VIDS[vi][1].indexOf(s.vf) < 0) { prevM = null; prevLine = i; prevVid = vi; continue; }
    const line = FT[i];
    const cur = res.map(function (re) { return matchesOf(re, line); });
    const usePrev = prevM && prevLine === i - 1 && prevVid === vi;
    let ok = true;
    for (let t = 0; t < N; t++) if (!cur[t].length && !(usePrev && prevM[t].length)) { ok = false; break; }
    if (ok) {
      const items = [], pw = usePrev ? wordCount(FT[prevLine]) : 0;
      for (let t = 0; t < N; t++) {
        if (usePrev) prevM[t].forEach(function (m) { items.push(mkItem(t, prevLine, m, FT[prevLine], 0)); });
        cur[t].forEach(function (m) { items.push(mkItem(t, i, m, line, pw)); });
      }
      chains(items, N, gap, anyOrder);
      if (ALL.length >= MAXHITS) break;
    }
    prevM = cur; prevLine = i; prevVid = vi;
  }
  finishPairs();
}
function chains(items, N, gap, anyOrder) {
  items.sort(function (a, b) { return a.l - b.l || a.s - b.s; });
  for (let a = 0; a < items.length; a++) {
    const first = items[a];
    if (!anyOrder && first.t !== 0) continue;
    const chain = [first];
    let used = 1 << first.t, cur = first, dsum = 0, good = true;
    for (let k = 1; k < N && good; k++) {
      let next = null;
      for (let b = a + 1; b < items.length; b++) {
        const c = items[b];
        if (used & (1 << c.t)) continue;
        if (!anyOrder && c.t !== k) continue;
        const d = c.w - (cur.w + cur.n);
        if (d < 0) continue;
        if (d > gap) break;
        next = c; dsum += d; break;
      }
      if (!next) good = false; else { chain.push(next); used |= 1 << next.t; cur = next; }
    }
    if (good) {
      const last = chain[chain.length - 1];
      ALL.push({ line: first.l, start: first.s, len: first.e - first.s, sec: null, two: true,
                 bLine: last.l, bStart: last.s, bLen: last.e - last.s, d: dsum,
                 parts: chain.map(function (c) { return [c.l, c.s, c.e - c.s, c.t]; }) });
      if (ALL.length >= MAXHITS) return;
    }
  }
}
function matchesOf(re, line) {
  const out = [];
  re.lastIndex = 0;
  let m;
  while ((m = re.exec(line)) !== null) {
    if (!m[0].length) { re.lastIndex++; continue; }
    out.push([m.index, m.index + m[0].length]);
  }
  return out;
}
/* true when this pair must be ignored because the first word already has a
   nearer partner (keeps one row per position instead of one per combination) */
function finishPairs() {
  ALL.sort(function (a, b) {
    return (a.line - b.line) || (a.start - b.start) || (a.d - b.d);
  });
  let out = [];
  let key = "";
  for (let i = 0; i < ALL.length; i++) {
    const h = ALL[i];
    const k = h.line + ":" + h.start;
    if (k === key) continue;
    key = k;
    out.push(h);
  }
  ALL = out;
}
/* every hit as one string plus the spans to highlight in it ([from, to, word number]) */
function hitText(h) {
  const t1 = LT[h.line];
  if (!h.two) return { text: t1, spans: [[h.start, h.start + h.len]] };
  const ps = h.parts, l2 = ps[ps.length - 1][0];
  if (l2 === h.line) return { text: t1, spans: ps.map(function (p) { return [p[1], p[1] + p[2], p[3]]; }) };
  const off = t1.length + 1;
  return { text: t1 + " " + LT[l2],
           spans: ps.map(function (p) { const o = p[0] === h.line ? 0 : off; return [p[1] + o, p[1] + p[2] + o, p[3]]; }) };
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* ---------- rendering ---------- */
const $ = function (id) { return document.getElementById(id); };
let GIDX = 0, MODE = 1, NW = 2, QRE = null, RD = null;
function el(t, c, x) {
  const e = document.createElement(t);
  if (c) e.className = c;
  if (x != null) e.textContent = x;
  return e;
}

function renderAll() {
  const target = Math.min(ALL.length, Math.max(PAGE, SHOWN));
  COUNTS = new Map();
  for (const h of ALL) COUNTS.set(LV[h.line], (COUNTS.get(LV[h.line]) || 0) + 1);
  const byCount = $("sort").value === "count";
  ALL.sort(byCount
    ? function (a, b) { return COUNTS.get(LV[b.line]) - COUNTS.get(LV[a.line]) || LV[a.line] - LV[b.line] || a.line - b.line || a.start - b.start; }
    : function (a, b) { return a.line - b.line || a.start - b.start; });
  $("results").innerHTML = "";
  LASTBOX = null; LASTVID = -1; SHOWN = 0; GIDX = 0;
  let guard = 0;
  while (SHOWN < target && guard++ < 2000) render();
  $("tools").hidden = false;
  updateMore();
  updateStatus();
}

function render() {
  const end = Math.min(ALL.length, SHOWN + PAGE);
  if (SHOWN >= end) return;
  const frag = document.createDocumentFragment();
  let box = LASTBOX, curVid = LASTVID;
  const ctx = currentSettings().ctx, fold = $("fold").value;
  for (let i = SHOWN; i < end; i++) {
    const h = ALL[i], vi = LV[h.line];
    if (vi !== curVid) { curVid = vi; box = newGroup(vi, GIDX++, fold); frag.appendChild(box); }
    box._in.appendChild(hitRow(h, ctx, i));
  }
  LASTVID = curVid; LASTBOX = box;
  $("results").appendChild(frag);
  SHOWN = end;
}

/* one collapsible box per video */
function newGroup(vi, gi, fold) {
  const v = VIDS[vi], n = COUNTS.get(vi) || 0;
  const open = fold === "all" || (fold === "first" && gi < 3);
  const box = el("section", "vid" + (open ? "" : " closed"));
  const hd = el("button", "vh");
  hd.type = "button"; hd.setAttribute("aria-expanded", open);
  hd.append(el("span", "chev", "▾"), el("span", "t", v[1]),
            el("span", "c", countLabel(n, "نتيجة واحدة", "نتيجتان", "نتائج", "نتيجة")));
  hd.onclick = function () { hd.setAttribute("aria-expanded", !box.classList.toggle("closed")); };
  const vb = el("div", "vb"), inn = el("div", "vbi");
  vb.appendChild(inn); box.append(hd, vb); box._in = inn;
  return box;
}
function foldAll(c) {
  document.querySelectorAll(".vid").forEach(function (b) {
    b.classList.toggle("closed", c);
    b.firstChild.setAttribute("aria-expanded", !c);
  });
}

function paintSave(b, key) {
  const on = !!BASKET[key];
  b.className = "add" + (on ? " picked" : "");
  b.textContent = on ? "★ محفوظ" : "☆ حفظ";
}
function syncSave(key) {
  document.querySelectorAll(".add").forEach(function (b) { if (b._key === key) paintSave(b, key); });
}

function hitRow(h, ctx, i) {
  const sec = secondOf(h.line, h.start), v = VIDS[LV[h.line]], key = pickKey(h, sec);
  const row = el("div", "hit");
  row.dataset.i = i;
  const tm = el("a", "time", hms(sec));
  tm.href = watchUrl(v[0], sec); tm.target = "_blank"; tm.rel = "noopener";
  tm.title = "افتح الفيديو عند هذه اللحظة";
  const body = el("div", "body"), sn = el("div", "snip");
  fillSnippet(sn, h, ctx);
  const more = el("button", "moreb", "… المزيد");
  more.type = "button"; more.title = "اقرأ الكلام قبل الكلمة وبعدها";
  more.onclick = function () { openReader(i, row); };
  sn.appendChild(more);
  const acts = el("div", "acts");
  const yt = el("a", "ytb", "يوتيوب");
  yt.href = watchUrl(v[0], sec); yt.target = "_blank"; yt.rel = "noopener";
  const copy = el("button", "cpy", "نسخ الرابط");
  copy.type = "button"; copy.onclick = function () { copyText(watchUrl(v[0], sec)); };
  const add = el("button", "add");
  add.type = "button"; add._key = key; paintSave(add, key);
  add.onclick = function () { togglePick(h, sec, key, add); syncSave(key); };
  const delBtn = el("button", "delb", "🗑 حذف الكلمة");
  delBtn.type = "button";
  delBtn.title = "حذف هذه الكلمة من التفريغ المحلي (مع إمكانية استرجاعها من الإعدادات)";
  delBtn.onclick = function (e) {
    e.stopPropagation();
    deleteWordHit(h, i, row);
  };
  acts.append(yt, copy, add, delBtn);
  body.append(sn, acts); row.append(tm, body);
  row.onclick = function (e) {
    if (e.target.closest("a,button") || String(window.getSelection())) return;
    openReader(i, row);
  };
  return row;
}

function pickKey(h, sec) {
  return VIDS[LV[h.line]][0] + "|" + sec + "|" + h.start + "|" + h.len + "|" +
         (h.bLine || h.line) + "|" + (h.bStart || 0);
}

/* the highlighted words with `ctx` characters of text around them; the cut is
   moved to a word boundary so no word is shown half-done */
function snippetParts(h, ctx) {
  const info = hitText(h);
  const text = info.text;
  const first = info.spans[0], last = info.spans[info.spans.length - 1];
  const half = Math.round(ctx / 2);
  let a = Math.max(0, first[0] - half);
  let b = Math.min(text.length, last[1] + half);
  while (a > 0 && text.charCodeAt(a) !== 32) a--;
  while (b < text.length && text.charCodeAt(b) !== 32) b++;
  const parts = [];
  let pos = a;
  for (let k = 0; k < info.spans.length; k++) {
    const sp = info.spans[k];
    if (sp[0] > pos) parts.push([text.slice(pos, sp[0]), 0]);
    parts.push([text.slice(sp[0], sp[1]), (sp[2] || 0) + 1]);
    pos = sp[1];
  }
  if (pos < b) parts.push([text.slice(pos, b), 0]);
  return { parts: parts, lead: a > 0, tail: b < text.length };
}

function fillSnippet(sn, h, ctx) {
  const sp = snippetParts(h, ctx);
  if (sp.lead) {
    const t = document.createElement("span");
    t.textContent = "…";
    sn.appendChild(t);
  }
  for (const part of sp.parts) {
    if (part[1]) {
      const mk = document.createElement("mark");
      if (part[1] > 1) mk.className = "bcd"[part[1] - 2];
      mk.textContent = part[0];
      sn.appendChild(mk);
    } else {
      const t = document.createElement("span");
      t.textContent = part[0];
      sn.appendChild(t);
    }
  }
  if (sp.tail) {
    const t = document.createElement("span");
    t.textContent = "…";
    sn.appendChild(t);
  }
}

function updateMore() {
  const more = document.getElementById("more");
  more.style.display = SHOWN < ALL.length ? "" : "none";
  more.textContent = "عرض المزيد (" + (ALL.length - SHOWN) + " متبقٍ)";
}
function updateStatus() {
  const two = QRE && QRE.res.length > 1, p = STAT.q.split("  ⟷  ");
  $("status").innerHTML = "<b>" + ALL.length + "</b> نتيجة في <b>" + COUNTS.size + "</b> فيديو" +
    (STAT.capped ? ' <span class="err">— وصلنا للحد الأقصى، جرّب كلمة أدق.</span>' : "") +
    (two ? '<span class="lg">' + p.map(function (w, k) { return '<mark class="' + ["", "b", "c", "d"][k] + '">' + escapeHtml(w) + "</mark>"; }).join("") + "</span>" : "");
}

/* ---------- the big reader (pops out of the clicked result) ---------- */
function openReader(i, from) {
  const h = ALL[i];
  if (!h) return;
  const L1 = h.line, L2 = h.bLine || h.line, vi = LV[L1];
  let lo = L1 - 1, hi = L2 + 1;
  if (lo < 0 || LV[lo] !== vi) lo = L1;
  if (hi >= LT.length || LV[hi] !== vi) hi = L2;
  const wasOpen = !!RD;
  RD = { i: i, lo: lo, hi: hi, vi: vi, from: from || (RD && RD.from) || null };
  $("reader").hidden = false;
  document.body.classList.add("noscroll");
  rdDraw(); rdFocus();
  const calm = document.body.classList.contains("calm") || matchMedia("(prefers-reduced-motion:reduce)").matches;
  const card = document.querySelector(".rd-card");
  if (calm || !card.animate) { if (!wasOpen) $("rdClose").focus(); return; }
  if (wasOpen) { $("rdBody").animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220 }); return; }
  if (RD.from) {
    const a = RD.from.getBoundingClientRect(), b = card.getBoundingClientRect();
    const dx = a.left + a.width / 2 - (b.left + b.width / 2), dy = a.top + a.height / 2 - (b.top + b.height / 2);
    card.animate([
      { transform: "translate(" + dx + "px," + dy + "px) scale(" + Math.max(.2, a.width / b.width) + "," + Math.max(.06, a.height / b.height) + ")", opacity: 0 },
      { transform: "none", opacity: 1 }], { duration: 440, easing: "cubic-bezier(.2,.85,.25,1)" });
  }
  $("rdClose").focus({ preventScroll: true });
}

function rdText(l, foc) {
  const t = LT[l], sp = [];
  QRE.res.forEach(function (re, k) {
    matchesOf(re, FT[l]).forEach(function (m) { sp.push([m[0], m[1], ["", "b", "c", "d"][k]]); });
  });
  sp.sort(function (x, y) { return x[0] - y[0]; });
  let out = "", pos = 0;
  for (const s of sp) {
    if (s[0] < pos) continue;
    const f = foc.some(function (q) { return q[0] === l && q[1] === s[0]; });
    out += escapeHtml(t.slice(pos, s[0])) + '<mark class="' + s[2] + (f ? " f" : "") + '">' +
           escapeHtml(t.slice(s[0], s[1])) + "</mark>";
    pos = s[1];
  }
  return out + escapeHtml(t.slice(pos));
}

function rdDraw() {
  const h = ALL[RD.i], v = VIDS[RD.vi];
  RD.sec = secondOf(h.line, h.start); RD.key = pickKey(h, RD.sec);
  const foc = h.two ? h.parts.map(function (p) { return [p[0], p[1]]; }) : [[h.line, h.start]];
  $("rdTitle").textContent = v[1];
  $("rdMeta").textContent = "عند " + hms(RD.sec) + " · النتيجة " + (RD.i + 1) + " من " + ALL.length;
  let html = "";
  if (RD.lo > 0 && LV[RD.lo - 1] === RD.vi) html += '<button class="rdm" type="button" data-d="-1">⬆ اعرض الدقيقة السابقة</button>';
  for (let l = RD.lo; l <= RD.hi; l++) {
    html += '<section class="min' + (l === h.line ? " cur" : "") + '"><a class="mt" target="_blank" rel="noopener" href="' +
      watchUrl(v[0], LS[l]) + '">' + hms(LS[l]) + "</a><p>" + rdText(l, foc) + "</p></section>";
  }
  if (RD.hi < LT.length - 1 && LV[RD.hi + 1] === RD.vi) html += '<button class="rdm" type="button" data-d="1">⬇ اعرض الدقيقة التالية</button>';
  $("rdBody").innerHTML = html;
  $("rdYt").href = watchUrl(v[0], RD.sec);
  $("rdPrev").disabled = RD.i <= 0; $("rdNext").disabled = RD.i >= ALL.length - 1;
  $("rdSave")._key = RD.key; paintSave($("rdSave"), RD.key);
}
function rdFocus() {
  const b = $("rdBody"), f = b.querySelector("mark.f");
  b.scrollTop = f ? Math.max(0, f.offsetTop - b.clientHeight / 3) : 0;
}
function rdGo(d) {
  const j = RD.i + d;
  if (j < 0 || j >= ALL.length) { toast(d > 0 ? "هذه آخر نتيجة" : "هذه أول نتيجة"); return; }
  while (SHOWN <= j && SHOWN < ALL.length) render();
  updateMore();
  openReader(j, null);
}
function closeReader() {
  if (!RD) return;
  const i = RD.i;
  RD = null;
  $("reader").hidden = true;
  document.body.classList.remove("noscroll");
  const r = document.querySelector('.hit[data-i="' + i + '"]');
  if (!r) return;
  const g = r.closest(".vid");
  if (g.classList.contains("closed")) { g.classList.remove("closed"); g.firstChild.setAttribute("aria-expanded", "true"); }
  r.scrollIntoView({ block: "center" });
  const b = r.querySelector(".moreb");
  if (b) b.focus({ preventScroll: true });
}

/* ---------- clipboard & toast ---------- */
function copyText(s) {
  const old = function () {
    const t = document.createElement("textarea");
    t.value = s; t.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(t); t.select();
    let r = false;
    try { r = document.execCommand("copy"); } catch (e) {}
    t.remove(); toast(r ? "تم النسخ" : "تعذّر النسخ");
  };
  if (navigator.clipboard && navigator.clipboard.writeText)
    navigator.clipboard.writeText(s).then(function () { toast("تم النسخ"); }, old);
  else old();
}
function toast(m) {
  const t = document.getElementById("toast");
  t.textContent = m; t.classList.add("on");
  setTimeout(function () { t.classList.remove("on"); }, 1500);
}

/* ---------- the file (basket) ---------- */
const BASKET_KEY = "fateera.basket.v3";
let BASKET = {};
function basketLoad() {
  try {
    const raw = localStorage.getItem(BASKET_KEY);
    if (raw) { const o = JSON.parse(raw); if (o && typeof o === "object") BASKET = o; }
  } catch (e) {}
}
function basketSave() {
  try { localStorage.setItem(BASKET_KEY, JSON.stringify(BASKET)); }
  catch (e) { toast("المتصفح لا يسمح بالحفظ"); }
}
function basketCount() { return Object.keys(BASKET).length; }
function basketList() {
  return Object.keys(BASKET).map(function (k) { return { key: k, r: BASKET[k] }; })
    .sort(function (a, b) {
      const x = a.r, y = b.r;
      return x.title < y.title ? -1 : x.title > y.title ? 1 : (x.sec - y.sec);
    });
}
function basketOrdered() { return basketList().map(function (x) { return x.r; }); }
function basketBar() {
  const n = basketCount();
  document.getElementById("bcount").innerHTML = n
    ? "المحفوظ: <b>" + n + "</b> نتيجة"
    : "لم تختر شيئًا بعد — اضغط «☆ حفظ» على أي نتيجة";
  document.getElementById("bhtml").disabled = !n;
  if (document.getElementById("bcsv")) document.getElementById("bcsv").disabled = !n;
  if (document.getElementById("btxt")) document.getElementById("btxt").disabled = !n;
  document.getElementById("blist").disabled = !n;
  document.getElementById("bclear").style.display = n ? "" : "none";
  document.querySelector(".basket").hidden = !n;
  if (!n) document.getElementById("drawer").classList.remove("on");
}
function drawerOpen() { return document.getElementById("drawer").classList.contains("on"); }
function drawerShow(on) {
  const d = document.getElementById("drawer");
  d.classList.toggle("on", !!on);
  if (on) {
    d.style.bottom = document.querySelector(".basket").offsetHeight + "px";
    renderDrawer();
  }
}
function plainText(s) { return String(s).replace(/[«»]/g, ""); }
function renderDrawer() {
  const box = document.getElementById("dlist");
  const items = basketList();
  document.getElementById("dcount").textContent = items.length ? "(" + items.length + ")" : "";
  box.innerHTML = "";
  if (!items.length) {
    const e = document.createElement("div");
    e.className = "dempty";
    e.textContent = "لا شيء محفوظ بعد — اضغط «☆ حفظ» على أي نتيجة.";
    box.appendChild(e);
    return;
  }
  items.forEach(function (it, i) {
    const r = it.r;
    const row = document.createElement("div");
    row.className = "ditem";
    const num = document.createElement("div");
    num.className = "i"; num.textContent = i + 1;
    const body = document.createElement("div");
    body.className = "dt";
    const t = document.createElement("div");
    t.className = "dh"; t.textContent = r.title;
    const meta = document.createElement("div");
    meta.className = "dm";
    const tm = document.createElement("span");
    tm.className = "time"; tm.textContent = hms(r.sec);
    const yt = document.createElement("a");
    yt.href = watchUrl(r.vid, r.sec); yt.target = "_blank"; yt.rel = "noopener";
    yt.textContent = "يوتيوب";
    yt.style.cssText = "color:var(--acc);font-size:12px;text-decoration:none;" +
      "border:1px solid var(--line);border-radius:6px;padding:4px 9px";
    const rm = document.createElement("button");
    rm.className = "rm"; rm.textContent = "حذف";
    rm.onclick = function () { basketRemove(it.key); };
    meta.append(tm, yt, rm);
    const sn = document.createElement("div");
    sn.className = "ds"; sn.textContent = plainText(r.snippet);
    body.append(t, meta, sn);
    row.append(num, body);
    box.appendChild(row);
  });
}
function basketRemove(key) {
  if (!BASKET[key]) return;
  delete BASKET[key];
  basketSave(); basketBar(); renderDrawer();
  document.querySelectorAll(".acts .add.picked").forEach(function (b) {
    if (b._key === key) { b.className = "add"; b.textContent = "☆ حفظ"; }
  });
  toast("أُزيلت من الملف");
}
function quoted(text, spans, lo, hi) {
  let out = (lo > 0 ? "…" : "");
  let pos = lo;
  for (const sp of spans) {
    out += text.slice(pos, sp[0]) + "«" + text.slice(sp[0], sp[1]) + "»";
    pos = sp[1];
  }
  return out + text.slice(pos, hi) + (hi < text.length ? "…" : "");
}
function togglePick(h, sec, key, btn) {
  if (BASKET[key]) { basketRemove(key); return; }
  const info = hitText(h);
  const text = info.text;
  const a = info.spans[0][0], b = info.spans[info.spans.length - 1][1];
  const lo = Math.max(0, a - 80), hi = Math.min(text.length, b + 80);
  BASKET[key] = {
    vid: VIDS[LV[h.line]][0],
    title: VIDS[LV[h.line]][1],
    sec: sec,
    snippet: quoted(text, info.spans, lo, hi),
    full: quoted(text, info.spans, 0, text.length)
  };
  btn.className = "add picked";
  btn.textContent = "★ محفوظ";
  basketSave(); basketBar();
  if (drawerOpen()) renderDrawer();
  toast("أُضيفت — المحفوظ " + basketCount());
}

/* ---------- the output page ---------- */
function escHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function quoteHtml(snippet) {
  return escHtml(snippet).replace(/«([^»]*)»/g, "<mark>$1</mark>");
}
function reportDate() {
  const months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                  "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
  const d = new Date();
  return d.getDate() + " " + months[d.getMonth()] + " " + d.getFullYear();
}
function countLabel(n, one, two, few, many) {
  if (n === 1) return one;
  if (n === 2) return two;
  if (n >= 3 && n <= 10) return n + " " + few;
  return n + " " + many;
}
const REPORT_CSS = `
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{background:#f4f1ea;color:#161d25;
    font:17px/1.95 "Segoe UI","Noto Naskh Arabic","Traditional Arabic",Tahoma,Arial,sans-serif;
    -webkit-text-size-adjust:100%}
  .wrap{max-width:820px;margin:0 auto;padding:32px 20px 70px}
  header.top{text-align:center;padding:8px 0 6px}
  h1{margin:0;font-size:30px;font-weight:700;letter-spacing:-.2px}
  .sub{margin:8px 0 0;color:#6b7684;font-size:15px}
  .meta{margin:14px 0 0;color:#8a94a0;font-size:13.5px}
  .how{max-width:680px;margin:24px auto 0;background:#fff;border:1px solid #e6e0d4;
    border-radius:14px;padding:13px 18px;font-size:15.5px;color:#3d4854;line-height:1.85}
  .how b{color:#161d25}
  .video{margin:32px 0 0}
  .video h2{font-size:20.5px;margin:0 0 3px;line-height:1.6}
  .vmeta{color:#8a94a0;font-size:13px;margin-bottom:12px}
  .clip{display:flex;gap:16px;background:#fff;border:1px solid #e6e0d4;border-radius:16px;
    padding:18px 20px;margin-bottom:14px;box-shadow:0 1px 2px rgba(20,25,32,.05)}
  .num{flex:0 0 34px;height:34px;border-radius:50%;background:#efe9dc;color:#6b5f47;
    font-size:15px;font-weight:700;display:flex;align-items:center;justify-content:center}
  .pane{flex:1;min-width:0}
  .when{display:flex;align-items:baseline;gap:8px}
  .lbl{color:#8a94a0;font-size:13px}
  .t{font:700 19px/1.2 Consolas,monospace;color:#2f4a6d;direction:ltr}
  .quote{margin:8px 0 14px;font-size:17.5px;line-height:2.05;color:#222b35;word-wrap:break-word}
  mark{background:#ffe9a8;color:#3a2f00;border-radius:3px;padding:0 2px}
  .morebox{margin:-4px 0 14px}
  .morebox summary{display:inline-flex;align-items:center;gap:6px;cursor:pointer;
    font-size:13.5px;color:#5c6a7a;background:#fbf9f4;border:1px solid #e6e0d4;
    border-radius:20px;padding:3px 12px;list-style:none;user-select:none}
  .morebox summary::-webkit-details-marker{display:none}
  .morebox summary:hover{color:#2f4a6d;border-color:#cfc7b7}
  .morebox summary::before{content:'+';font-weight:700;font-size:14px;line-height:1}
  .morebox[open] summary::before{content:'–'}
  .morebox .full{margin:10px 0 0;padding:12px 15px;background:#fbf9f4;
    border:1px solid #eee7da;border-radius:12px;font-size:16.5px;line-height:2;color:#2b3642}
  .acts{display:flex;gap:10px;flex-wrap:wrap}
  .btn{display:inline-flex;align-items:center;gap:8px;text-decoration:none;
    font-size:16px;font-weight:600;padding:11px 22px;border-radius:11px;
    border:1px solid transparent;min-height:46px}
  .btn .ico{font-size:15px;line-height:1}
  .yt{background:#c4302b;color:#fff}
  .yt:hover{background:#a82621}
  .st{background:#274060;color:#fff}
  .st:hover{background:#1d3149}
  .btn:focus-visible{outline:3px solid #f0b429;outline-offset:2px}
  footer{margin-top:44px;text-align:center;color:#9aa3ae;font-size:12.5px}
  @media (max-width:560px){
    .wrap{padding:22px 14px 44px}
    h1{font-size:25px}
    .clip{padding:15px 14px;gap:10px;border-radius:14px}
    .quote{font-size:16.5px;line-height:2}
    .btn{flex:1;justify-content:center;font-size:15.5px;padding:12px 10px}
    .num{flex-basis:28px;height:28px;font-size:13px}
  }
  @media print{
    @page{margin:16mm}
    body{background:#fff;font-size:12.5pt}
    .wrap{max-width:none;padding:0}
    .how{display:none}
    .clip{box-shadow:none;break-inside:avoid;page-break-inside:avoid;margin-bottom:9mm;
      border-color:#ccc}
    .video h2{break-after:avoid;page-break-after:avoid}
    .btn{background:#fff !important;color:#000 !important;border:1px solid #888;
      padding:5px 12px;min-height:0;font-size:11pt}
    .morebox summary{display:none}
    .morebox .full{border-color:#ccc;background:#fff;font-size:11pt;padding:6px 8px}
    footer{display:none}
  }
`;

function reportHtml(items) {
  const groups = [], byId = {};
  for (const r of items) {
    if (!byId[r.vid]) { byId[r.vid] = { vid: r.vid, title: r.title, clips: [] }; groups.push(byId[r.vid]); }
    byId[r.vid].clips.push(r);
  }
  let n = 0, body = "";
  for (const g of groups) {
    g.clips.sort(function (a, b) { return a.sec - b.sec; });
    body += '<section class="video"><h2>' + escHtml(g.title) + "</h2>" +
      '<div class="vmeta">' + countLabel(g.clips.length, "مقطع واحد", "مقطعان", "مقاطع", "مقطعًا") + "</div>";
    for (const c of g.clips) {
      n++;
      const longer = c.full && c.full.length > c.snippet.length + 30;
      body += '<article class="clip"><div class="num">' + n + '</div><div class="pane">' +
        '<div class="when"><span class="lbl">الدقيقة</span>' +
        '<span class="t">' + hms(c.sec) + "</span></div>" +
        '<p class="quote">' + quoteHtml(c.snippet) + "</p>" +
        (longer ? '<details class="morebox"><summary>عرض المزيد</summary><div class="full">' +
          quoteHtml(c.full) + "</div></details>" : "") +
        '<div class="acts">' +
        '<a class="btn yt" target="_blank" rel="noopener" href="' + watchUrl(c.vid, c.sec) + '">' +
          '<span class="ico" aria-hidden="true">▶</span>يوتيوب</a>' +
        '<a class="btn st" target="_blank" rel="noopener" ' +
          'href="https://studio.youtube.com/video/' + c.vid + '/edit">' +
          '<span class="ico" aria-hidden="true">✂</span>استوديو</a>' +
        "</div></div></article>";
    }
    body += "</section>";
  }
  const vids = groups.length;
  return "<!doctype html>\n<html lang=\"ar\" dir=\"rtl\">\n<head>\n<meta charset=\"utf-8\">\n" +
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n' +
    "<title>مقاطع مختارة — " + escapeHtml(document.title) + "</title>\n<style>" + REPORT_CSS + "</style>\n</head>\n<body>\n" +
    '<div class="wrap">\n<header class="top">' +
    "<h1>مقاطع مختارة</h1>" +
    '<div class="sub">من ' + escapeHtml(document.title) + '</div>' +
    '<div class="meta">' + countLabel(n, "مقطع واحد", "مقطعان", "مقاطع", "مقطعًا") + " في " +
      countLabel(vids, "فيديو واحد", "فيديوهين", "فيديوهات", "فيديو") + " · " + reportDate() +
    "</div></header>\n" +
    '<div class="how"><b>كيف تستخدم الصفحة:</b> اضغط <b>يوتيوب</b> لتشغيل الفيديو من الثانية ' +
    "المكتوبة، واضغط <b>استوديو</b> لفتح الفيديو في محرّر القناة. وإن أردت الكلام كاملًا اضغط " +
    "<b>عرض المزيد</b> تحت المقتطف.</div>\n" +
    body +
    "\n<footer>هذه الصفحة تعمل بدون إنترنت · الحاجة الوحيدة للشبكة هي فتح الروابط.</footer>" +
    "\n</div>\n</body>\n</html>";
}

function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(function () { URL.revokeObjectURL(a.href); }, 8000);
}
function ymd() {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" +
         String(d.getDate()).padStart(2, "0");
}
function downloadReport() {
  if (!basketCount()) { toast("لم تختر نتائج بعد"); return; }
  download(new Blob([reportHtml(basketOrdered())], { type: "text/html;charset=utf-8" }),
           "مقاطع مختارة " + ymd() + ".html");
  toast("تم تحميل الصفحة");
}

function downloadCsv() {
  if (!basketCount()) { toast("لم تختر نتائج بعد"); return; }
  const items = basketOrdered();
  let csv = "\uFEFFالعنوان,الدقيقة,رابط يوتيوب,رابط استوديو,المقتطف\n";
  for (const r of items) {
    const q = function (s) { return '"' + String(s || "").replace(/"/g, '""') + '"'; };
    csv += [q(r.title), q(hms(r.sec)), q(watchUrl(r.vid, r.sec)),
            q("https://studio.youtube.com/video/" + r.vid + "/edit"),
            q(plainText(r.snippet))].join(",") + "\n";
  }
  download(new Blob([csv], { type: "text/csv;charset=utf-8" }), "مقاطع مختارة " + ymd() + ".csv");
  toast("تم تصدير ملف CSV");
}

function downloadTxt() {
  if (!basketCount()) { toast("لم تختر نتائج بعد"); return; }
  const items = basketOrdered();
  let txt = "مقاطع مختارة (" + reportDate() + ")\n========================================\n\n";
  for (let i = 0; i < items.length; i++) {
    const r = items[i];
    txt += (i + 1) + ") " + r.title + "\n";
    txt += "الدقيقة: " + hms(r.sec) + "\n";
    txt += "الرابط: " + watchUrl(r.vid, r.sec) + "\n";
    txt += "المقتطف:\n" + plainText(r.snippet) + "\n\n";
    txt += "----------------------------------------\n\n";
  }
  download(new Blob([txt], { type: "text/plain;charset=utf-8" }), "مقاطع مختارة " + ymd() + ".txt");
  toast("تم تصدير ملف النص");
}

/* ---------- boot ---------- */
function setProgress(p, msg) {
  document.getElementById("pbar").style.width = p + "%";
  if (msg) document.getElementById("pmsg").textContent = msg;
}

/* ---------- Deleted Words Management ---------- */
let ORIG_LT = [];
let DELETED_WORDS = {};

function loadDeletedWords() {
  try {
    const raw = localStorage.getItem("TF_DELETED_WORDS");
    DELETED_WORDS = raw ? JSON.parse(raw) : {};
  } catch (e) {
    DELETED_WORDS = {};
  }
}

function saveDeletedWords() {
  try {
    localStorage.setItem("TF_DELETED_WORDS", JSON.stringify(DELETED_WORDS));
  } catch (e) {}
}

function applyLineDeletions(lineIdx, items) {
  if (lineIdx < 0 || lineIdx >= LT.length || !ORIG_LT[lineIdx]) return;
  let t = ORIG_LT[lineIdx];
  // Sort descending by start pos so earlier slices do not shift later positions
  items.sort(function (a, b) { return (b.start || 0) - (a.start || 0); });
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    if (it.start !== undefined && it.len && (it.start + it.len) <= t.length && t.substr(it.start, it.len) === it.word) {
      t = t.slice(0, it.start) + t.slice(it.start + it.len);
    } else if (it.word && t.indexOf(it.word) >= 0) {
      t = t.replace(it.word, "");
    }
  }
  t = t.replace(/\s+/g, " ").trim();
  LT[lineIdx] = t;
  FT[lineIdx] = LETTERS.test(t) ? letterFold(t) : t;
}

function rebuildLine(lineIdx) {
  if (lineIdx < 0 || lineIdx >= LT.length || !ORIG_LT[lineIdx]) return;
  const lineItems = [];
  for (const k in DELETED_WORDS) {
    if (DELETED_WORDS[k] && DELETED_WORDS[k].line === lineIdx) {
      lineItems.push(DELETED_WORDS[k]);
    }
  }
  if (!lineItems.length) {
    LT[lineIdx] = ORIG_LT[lineIdx];
    FT[lineIdx] = LETTERS.test(LT[lineIdx]) ? letterFold(LT[lineIdx]) : LT[lineIdx];
  } else {
    applyLineDeletions(lineIdx, lineItems);
  }
}

function applyDeletedWords() {
  loadDeletedWords();
  const keys = Object.keys(DELETED_WORDS);
  if (!keys.length) {
    updateDeletedUI();
    return;
  }
  const byLine = {};
  for (let i = 0; i < keys.length; i++) {
    const it = DELETED_WORDS[keys[i]];
    if (!it || it.line === undefined || it.line >= LT.length) continue;
    if (!byLine[it.line]) byLine[it.line] = [];
    byLine[it.line].push(it);
  }
  for (const lStr in byLine) {
    const lIdx = parseInt(lStr, 10);
    applyLineDeletions(lIdx, byLine[lStr]);
  }
  updateDeletedUI();
}

function deleteWordHit(h, idx, rowEl) {
  const lineIdx = h.line;
  const matchedWord = (LT[lineIdx] && LT[lineIdx].substr(h.start, h.len)) || "";
  if (!matchedWord) return;

  if (!confirm('هل تريد حذف كلمة «' + matchedWord + '» من هذا الموضع في التفريغ؟\n\n(يمكنك استرجاعها في أي وقت من قائمة الإعدادات ⚙)')) return;

  const sec = secondOf(h.line, h.start);
  const v = VIDS[LV[h.line]] || ["", "فيديو غير محدد"];
  const key = "del_" + lineIdx + "_" + h.start + "_" + Date.now();

  DELETED_WORDS[key] = {
    key: key,
    line: lineIdx,
    word: matchedWord,
    start: h.start,
    len: h.len,
    vid: v[0],
    vtitle: v[1],
    sec: sec,
    timeStr: hms(sec),
    date: new Date().toLocaleDateString("ar-EG")
  };

  saveDeletedWords();
  rebuildLine(lineIdx);
  updateDeletedUI();

  if (rowEl) {
    rowEl.style.transition = "opacity 0.3s, background 0.3s";
    rowEl.style.opacity = "0.35";
    const delBtn = rowEl.querySelector(".delb");
    if (delBtn) {
      delBtn.textContent = "✓ تم الحذف";
      delBtn.disabled = true;
      delBtn.style.color = "var(--ok)";
      delBtn.style.borderColor = "var(--ok)";
    }
  }
  toast("تم حذف كلمة «" + matchedWord + "» بنجاح! يمكنك استرجاعها من الإعدادات ⚙");
}

function restoreWord(key) {
  const it = DELETED_WORDS[key];
  if (!it) return;

  const lineIdx = it.line;
  delete DELETED_WORDS[key];
  saveDeletedWords();

  rebuildLine(lineIdx);
  updateDeletedUI();
  toast("تم استرجاع كلمة «" + it.word + "» بنجاح!");

  const qVal = $("q") ? $("q").value.trim() : "";
  if (qVal) search();
}

function restoreAllDeleted() {
  const keys = Object.keys(DELETED_WORDS);
  if (!keys.length) return;
  if (!confirm("هل تريد استرجاع جميع الكلمات المحذوفة (" + keys.length + " كلمة)؟")) return;

  const linesToRebuild = {};
  for (let i = 0; i < keys.length; i++) {
    const it = DELETED_WORDS[keys[i]];
    if (it && it.line !== undefined) linesToRebuild[it.line] = true;
  }

  DELETED_WORDS = {};
  saveDeletedWords();

  for (const lStr in linesToRebuild) {
    const lIdx = parseInt(lStr, 10);
    if (ORIG_LT[lIdx]) {
      LT[lIdx] = ORIG_LT[lIdx];
      FT[lIdx] = LETTERS.test(LT[lIdx]) ? letterFold(LT[lIdx]) : LT[lIdx];
    }
  }

  updateDeletedUI();
  toast("تم استرجاع جميع الكلمات المحذوفة بنجاح!");

  const qVal = $("q") ? $("q").value.trim() : "";
  if (qVal) search();
}

function updateDeletedUI() {
  const countEl = document.getElementById("delCount");
  const listEl = document.getElementById("delList");
  const restoreAllBtn = document.getElementById("delRestoreAll");
  const keys = Object.keys(DELETED_WORDS);

  if (countEl) countEl.textContent = keys.length;
  if (restoreAllBtn) restoreAllBtn.style.display = keys.length > 0 ? "inline-block" : "none";

  if (!listEl) return;
  if (!keys.length) {
    listEl.innerHTML = '<div style="color:var(--dim); text-align:center; padding:12px 0;">لا توجد كلمات محذوفة حالياً.</div>';
    return;
  }

  let html = "";
  for (let i = 0; i < keys.length; i++) {
    const k = keys[i];
    const it = DELETED_WORDS[k];
    html += '<div style="display:flex; justify-content:space-between; align-items:center; padding:7px 8px; border-bottom:1px solid var(--line); gap:8px;">' +
      '<div style="min-width:0; flex:1; text-align:right;">' +
        '<b style="color:var(--red); font-size:13px;">«' + escapeHtml(it.word) + '»</b> ' +
        '<span style="color:var(--dim); font-size:11.5px;">[' + escapeHtml(it.timeStr) + '] ' + escapeHtml((it.vtitle || "").slice(0, 36)) + '</span>' +
      '</div>' +
      '<button class="sm" type="button" onclick="restoreWord(\'' + k + '\')" style="color:var(--acc); border:1px solid var(--line); padding:3px 8px; font-size:11.5px; border-radius:5px; background:var(--bg); cursor:pointer;">↺ استرجاع</button>' +
    '</div>';
  }
  listEl.innerHTML = html;
}

function boot() {
  if (B85SRC) {
    setProgress(3, "فك الضغط…");
    try {
      const u8 = decodeB85(B85SRC, B85LEN);
      if (B85_EL) B85_EL.remove();
      new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream("gzip")))
        .arrayBuffer()
        .then(function (buf) { boot2(buf); })
        .catch(function (e) {
          document.getElementById("pmsg").textContent = "فشل فك الضغط: " + e;
        });
    } catch (e) {
      document.getElementById("pmsg").textContent = "هذا المتصفح لا يدعم فك الضغط. استخدم النسخة العادية.";
    }
    return;
  }
  if (GZSRC) {
    setProgress(3, "فك الضغط…");
    try {
      const bin = atob(GZSRC);
      const u8 = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream("gzip")))
        .arrayBuffer()
        .then(function (buf) { boot2(buf); })
        .catch(function (e) {
          document.getElementById("pmsg").textContent = "فشل فك الضغط: " + e;
        });
    } catch (e) {
      document.getElementById("pmsg").textContent = "هذا المتصفح لا يدعم فك الضغط. استخدم النسخة العادية.";
    }
    return;
  }
  boot2(RAWSRC);
}
let BOOTMS = 0;
function boot2(text) {
  setProgress(5, "تحليل الملف…");
  if (!text) {
    document.getElementById("pmsg").innerHTML =
      '<span class="err">لا توجد بيانات في هذه الصفحة. أعد بناءها من الأداة.</span>';
    return;
  }
  setTimeout(function () {
    const t0 = Date.now();
    try {
      parseAll(text);
    applyDeletedWords();
    } catch (e) {
      document.getElementById("pmsg").innerHTML =
        '<span class="err">تعذّر قراءة الملف: ' + escapeHtml(e.message) + "</span>";
      return;
    }
    BOOTMS = Date.now() - t0;
    setProgress(70, "تجهيز البحث…");
    setTimeout(function () {
      document.getElementById("splash").style.display = "none";
      $("sub").textContent = "جاهز — " + VIDS.length.toLocaleString("en") + " فيديو يمكنك البحث فيها.";
      document.getElementById("q").focus();
    }, 30);
  }, 30);
}

/* ---------- settings that survive a reload ---------- */
const SET_KEY = "fateera.settings.v3";
const SETTINGS = ["loose", "ctx", "fs", "theme", "orderany", "hue", "font", "fold", "sort", "motion", "rdfs"];

function saveSettings() {
  const o = {};
  for (const k of SETTINGS) {
    const e = $(k);
    if (e) o[k] = e.type === "checkbox" ? e.checked : e.value;
  }
  try { localStorage.setItem(SET_KEY, JSON.stringify(o)); } catch (e) {}
}
function loadSettings() {
  let o = null;
  try { o = JSON.parse(localStorage.getItem(SET_KEY) || "null"); } catch (e) {}
  if (!o) return;
  for (const k of SETTINGS) {
    const e = $(k);
    if (!e || o[k] === undefined || o[k] === null) continue;
    if (e.type === "checkbox") e.checked = !!o[k]; else e.value = o[k];
  }
}
function resetSettings() {
  for (const k of SETTINGS) {
    const e = $(k);
    if (!e) continue;
    if (e.type === "checkbox") e.checked = e.defaultChecked;
    else if (e.tagName === "SELECT") { for (const o of e.options) if (o.defaultSelected) e.value = o.value; }
    else e.value = e.defaultValue;
  }
  saveSettings(); applyLook();
  if (ALL.length) renderAll();
  toast("رجعت الإعدادات كما كانت");
}
function applyLook() {
  const st = document.documentElement.style;
  st.setProperty("--fs", (parseInt($("fs").value, 10) || 16) + "px");
  st.setProperty("--h", $("hue").value || 175);
  st.setProperty("--rdfs", (parseInt($("rdfs").value, 10) || 20) + "px");
  const th = $("theme").value;
  const dk = th === "dark" || (th === "auto" && matchMedia("(prefers-color-scheme:dark)").matches);
  document.documentElement.classList.toggle("dark", dk);
  document.body.classList.toggle("dark", dk);
  st.colorScheme = dk ? "dark" : "light";
  document.body.classList.toggle("naskh", $("font").value === "naskh");
  document.body.classList.toggle("calm", $("motion").checked);
}

/* ---------- search box: one word, or two words close together ---------- */
function setMode(m) {
  MODE = m;
  $("m1").classList.toggle("on", m === 1); $("m2").classList.toggle("on", m === 2);
  $("m1").setAttribute("aria-selected", m === 1); $("m2").setAttribute("aria-selected", m === 2);
  $("pair").hidden = m !== 2; showWords();
  $("lab1").textContent = m === 2 ? "الكلمة الأولى" : "اكتب كلمة أو جملة";
  $("q").placeholder = m === 2 ? "مثال: الهداية" : "مثال: الصبر على البلاء";
  proxSum();
}
function showWords() {
  document.querySelectorAll("[data-n]").forEach(function (e) { e.hidden = !(MODE === 2 && parseInt(e.dataset.n, 10) <= NW); });
  $("addw").hidden = MODE !== 2 || NW >= 4;
  $("addw").textContent = NW === 2 ? "＋ أضف كلمة ثالثة" : "＋ أضف كلمة رابعة";
  proxSum();
}
function proxSum() {
  const g = parseInt($("gap").value, 10) || 0;
  const ws = ["q", "q2", "q3", "q4"].slice(0, NW).map(function (id) { return "<b>«" + escapeHtml($(id).value.trim() || "…") + "»</b>"; });
  $("pxsum").innerHTML = "سنعرض الأماكن التي قيلت فيها " + ws.join(" و") + " " +
    (g ? "وبين كل كلمتين متتاليتين حتى " + g + " كلمة." : "متجاورة تمامًا.");
}

/* ---------- search history (small pop-up under the 🕘 button) ---------- */
const HIST_KEY = "fateera.history.v1";
function histGet() {
  try { const a = JSON.parse(localStorage.getItem(HIST_KEY) || "[]"); return Array.isArray(a) ? a : []; } catch (e) { return []; }
}
function histSet(a) { try { localStorage.setItem(HIST_KEY, JSON.stringify(a.slice(0, 15))); } catch (e) {} }
function histAdd(words, gap, any) {
  const a = histGet().filter(function (x) { return x.w.join("|") !== words.join("|"); });
  a.unshift({ w: words, g: gap, o: any });
  histSet(a);
}
function histDraw() {
  const box = $("hlist"), a = histGet();
  box.innerHTML = "";
  $("hclear").hidden = !a.length;
  if (!a.length) { box.appendChild(el("div", "hempty", "لا توجد عمليات بحث سابقة")); return; }
  a.forEach(function (x, i) {
    const row = el("div", "hitem"), b = el("button", "hi", x.w.join(" + ")), r = el("button", "hx", "✕");
    b.type = r.type = "button";
    b.title = x.w.length > 1 ? "المسافة: " + x.g + " كلمة" : "";
    r.setAttribute("aria-label", "حذف");
    b.onclick = function () { histRun(x); };
    r.onclick = function (e) { e.stopPropagation(); const l = histGet(); l.splice(i, 1); histSet(l); histDraw(); };
    row.append(b, r); box.appendChild(row);
  });
}
function histRun(x) {
  NW = Math.max(2, x.w.length);
  ["q", "q2", "q3", "q4"].forEach(function (id, k) { $(id).value = x.w[k] || ""; });
  if (x.w.length > 1) { $("gap").value = x.g; $("orderany").checked = x.o !== false; }
  setMode(x.w.length > 1 ? 2 : 1);
  $("hpop").hidden = true;
  search();
}
function sheet(on) {
  $("sheet").classList.toggle("on", on);
  $("sback").hidden = !on;
}

/* ---------- ui wiring ---------- */
$("m1").onclick = function () { setMode(1); $("q").focus(); };
$("m2").onclick = function () { setMode(2); ($("q").value.trim() ? $("q2") : $("q")).focus(); };
$("go").onclick = search;
["q", "q2", "q3", "q4"].forEach(function (id) {
  $(id).addEventListener("keydown", function (e) { if (e.key === "Enter") search(); });
  $(id).addEventListener("input", proxSum);
});
$("gap").addEventListener("input", proxSum);
$("gap").addEventListener("keydown", function (e) { if (e.key === "Enter") search(); });
bindChips();
$("addw").onclick = function () { if (NW < 4) { NW++; showWords(); $("q" + NW).focus(); } };
document.querySelectorAll(".rx").forEach(function (b) {
  b.onclick = function () {
    if (b.dataset.r === "3") $("q3").value = $("q4").value;
    $("q4").value = "";
    NW--; showWords();
  };
});
$("histBtn").onclick = function () { const p = $("hpop"); p.hidden = !p.hidden; if (!p.hidden) histDraw(); };
$("hclear").onclick = function () { histSet([]); histDraw(); };
document.addEventListener("click", function (e) { if (!e.target.closest(".hwrap")) $("hpop").hidden = true; });
$("more").onclick = function () { render(); updateMore(); };
$("foldNone").onclick = function () { foldAll(true); };
$("foldAll").onclick = function () { foldAll(false); };
$("settingsBtn").onclick = function () { sheet(true); };
$("sclose").onclick = $("sback").onclick = function () { sheet(false); };
$("sreset").onclick = resetSettings;
for (const k of SETTINGS) {
  $(k).addEventListener("change", function () {
    saveSettings(); applyLook();
    if ((k === "ctx" || k === "fold" || k === "sort") && ALL.length) renderAll();
  });
}

$("rdClose").onclick = $("rdBack").onclick = closeReader;
$("rdPrev").onclick = function () { rdGo(-1); };
$("rdNext").onclick = function () { rdGo(1); };
$("rdBody").onclick = function (e) {
  const b = e.target.closest(".rdm");
  if (!b) return;
  const d = parseInt(b.dataset.d, 10), box = $("rdBody"), top = box.scrollTop, hh = box.scrollHeight;
  if (d < 0) RD.lo--; else RD.hi++;
  rdDraw();
  box.scrollTop = top + (d < 0 ? box.scrollHeight - hh : 0);
};
function rdFont(d) {
  $("rdfs").value = Math.max(15, Math.min(34, (parseInt($("rdfs").value, 10) || 20) + d * 2));
  saveSettings(); applyLook();
}
$("rdSmall").onclick = function () { rdFont(-1); };
$("rdBig").onclick = function () { rdFont(1); };
$("rdSave").onclick = function () { togglePick(ALL[RD.i], RD.sec, RD.key, this); syncSave(RD.key); };
$("rdCopy").onclick = function () {
  const txt = Array.prototype.map.call(document.querySelectorAll("#rdBody .min p"), function (p) { return p.textContent; }).join("\n\n");
  copyText(VIDS[RD.vi][1] + "\n" + watchUrl(VIDS[RD.vi][0], RD.sec) + "\n\n" + txt);
};

(function basketUI() {
  $("bhtml").onclick = downloadReport;
  $("bcsv").onclick = downloadCsv;
  $("btxt").onclick = downloadTxt;
  $("blist").onclick = function () { drawerShow(!drawerOpen()); };
  $("dclose").onclick = function () { drawerShow(false); };
  $("bclear").onclick = function () {
    if (!basketCount()) return;
    if (!confirm("هل تريد مسح كل المحفوظات؟")) return;
    BASKET = {};
    basketSave(); basketBar();
    document.querySelectorAll(".add.picked").forEach(function (b) { paintSave(b, b._key); });
    toast("تم المسح");
  };
  document.addEventListener("keydown", function (e) {
    if (RD) {
      if (e.key === "Escape") closeReader();
      else if (e.key === "ArrowLeft") rdGo(1);
      else if (e.key === "ArrowRight") rdGo(-1);
      return;
    }
    if (e.key === "Escape") {
      if (!$("hpop").hidden) $("hpop").hidden = true;
      else if ($("sheet").classList.contains("on")) sheet(false);
      else if (drawerOpen()) drawerShow(false);
    } else if (e.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) {
      e.preventDefault(); $("q").focus();
    }
  });
})();

matchMedia("(prefers-color-scheme:dark)").addEventListener("change", applyLook);
loadSettings();
applyLook();
basketLoad();
basketBar();
setMode(1);
boot();
</script>
</body>
</html>

"""


SAFE85 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%()*+-;=?@^_{|}~./:["


def encode_safe85(data):
    n = len(data)
    chunks = []
    i = 0
    while i < n:
        rem = n - i
        if rem >= 4:
            v = (data[i] << 24) | (data[i+1] << 16) | (data[i+2] << 8) | data[i+3]
            u = v
            c4 = u % 85; u //= 85
            c3 = u % 85; u //= 85
            c2 = u % 85; u //= 85
            c1 = u % 85; u //= 85
            c0 = u
            chunks.append(SAFE85[c0] + SAFE85[c1] + SAFE85[c2] + SAFE85[c3] + SAFE85[c4])
            i += 4
        else:
            u = 0
            for k in range(rem):
                u |= (data[i + k] << (24 - k * 8))
            c = [0] * 5
            for k in range(4, -1, -1):
                c[k] = u % 85
                u //= 85
            s = "".join(SAFE85[c[k]] for k in range(rem + 1))
            chunks.append(s)
            i += rem
    return "".join(chunks)


def build(src, out, compress=False, title="بحث تفريغ القناة", sub="", zopfli=False):
    videos, lines = read_machine(src)

    JUNK_RE = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640\u200C-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]')
    cleaned_lines = []
    for l in lines:
        t = l[2]
        if JUNK_RE.search(t):
            t = JUNK_RE.sub("", t)
        cleaned_lines.append([l[0], l[1], t, l[3]])

    vid_line_counts = [0] * len(videos)
    for l in cleaned_lines:
        vid_line_counts[l[1]] += 1
    v_compact = [[v[0], v[1], v[2], vid_line_counts[i]] for i, v in enumerate(videos)]

    starts = [l[0] for l in cleaned_lines]

    ascii_offs = []
    for l in cleaned_lines:
        offs_str = l[3].strip()
        if not offs_str:
            ascii_offs.append("")
            continue
        nums = [int(x) for x in offs_str.split()]
        ascii_offs.append("".join(chr(35 + x) for x in nums))

    if not sub:
        hours = int(round(sum(max(0, v[2]) for v in videos) / 3600.0))
        sub = "%d فيديو" % len(videos) + (" · %d ساعة" % hours if hours else "")
    title = (title or "").replace("<", "&lt;").replace(">", "&gt;")
    sub = (sub or "").replace("<", "&lt;").replace(">", "&gt;")

    if compress:
        word_counter = Counter()
        for l in cleaned_lines:
            word_counter.update(l[2].split())

        dict_words = [w for w, _ in word_counter.most_common()]
        word_to_id = {w: i for i, w in enumerate(dict_words)}
        dict_str = "\n".join(dict_words)

        word_counts = []
        varint_bytes = bytearray()
        for l in cleaned_lines:
            ws = l[2].split()
            word_counts.append(len(ws))
            for w in ws:
                v = word_to_id[w]
                while v >= 128:
                    varint_bytes.append((v & 127) | 128)
                    v >>= 7
                varint_bytes.append(v)

        meta = {
            "v": v_compact,
            "s": starts,
            "o": ascii_offs,
            "w": word_counts,
            "d": dict_str
        }
        meta_json = json.dumps(meta, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        combined = bytearray()
        combined.extend(struct.pack(">I", len(meta_json)))
        combined.extend(meta_json)
        combined.extend(varint_bytes)

        if zopfli:
            try:
                import zopfli.gzip as z_gzip
                gz = z_gzip.compress(bytes(combined))
            except ImportError:
                gz = gzip.compress(bytes(combined), 9)
        else:
            gz = gzip.compress(bytes(combined), 9)

        b85 = encode_safe85(gz)
        html = (TEMPLATE
                .replace("__RAW__", "")
                .replace("__B85__", b85)
                .replace("__B85LEN__", str(len(gz)))
                .replace("__GZ__", "null")
                .replace("__TITLE__", title)
                .replace("__SUB__", sub))
    else:
        texts = [l[2] for l in cleaned_lines]
        payload = {
            "v": v_compact,
            "s": starts,
            "t": texts,
            "o": ascii_offs
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        html = (TEMPLATE
                .replace("__RAW__", raw)
                .replace("__B85__", "")
                .replace("__B85LEN__", "0")
                .replace("__GZ__", "null")
                .replace("__TITLE__", title)
                .replace("__SUB__", sub))

    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    return len(videos), len(lines), os.path.getsize(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=None,
                    help="machine transcript (default: newest *_unformatted.txt in output/)")
    ap.add_argument("--out", dest="out", default=None)
    ap.add_argument("--compress", action="store_true")
    ap.add_argument("--zopfli", action="store_true", help="use Zopfli for maximum compression")
    ap.add_argument("--title", default="بحث تفريغ القناة")
    ap.add_argument("--sub", default="")
    a = ap.parse_args()

    src = a.src
    if not src:
        folder = os.path.join(ROOT, "output")
        cands = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.endswith("_unformatted.txt")]
        if not cands:
            sys.exit("لا يوجد ملف تفريغ في output/ — شغّل المرحلة الرابعة أولًا.")
        src = max(cands, key=os.path.getmtime)
    out = a.out or os.path.join(ROOT, "output", "search.html")

    v, l, size = build(src, out, a.compress, a.title, a.sub, zopfli=a.zopfli)
    print("videos: %d | lines: %d | %.1f MB -> %s" % (v, l, size / 1048576, out))


if __name__ == "__main__":
    main()
