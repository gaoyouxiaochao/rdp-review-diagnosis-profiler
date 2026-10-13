# -*- coding: utf-8 -*-
"""报告样式。全部走 CSS 变量，禁止在组件里硬编码颜色。"""

CSS = """
:root{
  --bg:#f6f7f9; --surface:#ffffff; --border:#e4e7ec; --border-strong:#d0d5dd;
  --text:#1a1d21; --text-2:#5b6472; --text-3:#8993a1;
  --primary:#1f6feb; --primary-soft:#eaf2ff;
  --up:#c0392b; --up-soft:#fdeceb;
  --down:#0f8a4f; --down-soft:#e7f6ee;
  --warn:#b45309; --warn-soft:#fef4e7;
  --neutral-soft:#f1f3f6;
  --radius:12px; --radius-sm:8px;
  --mono:"Cascadia Mono",Consolas,"Courier New",monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI","Microsoft YaHei","PingFang SC",system-ui,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.65;font-size:14.5px}
.wrap{max-width:1180px;margin:0 auto;padding:28px 22px 64px}
header.hero{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:26px 26px 20px;margin-bottom:18px}
.kicker{font-size:12px;letter-spacing:.08em;color:var(--text-3);text-transform:uppercase}
h1{font-size:24px;margin:6px 0 8px;font-weight:650}
.hero p{color:var(--text-2);font-size:13.5px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chip{font-size:12px;padding:3px 10px;border-radius:99px;background:var(--neutral-soft);
  color:var(--text-2);border:1px solid var(--border)}
.chip.ok{background:var(--down-soft);color:var(--down)}
.chip.warn{background:var(--warn-soft);color:var(--warn)}
h2{font-size:18px;margin:30px 0 12px;padding-left:11px;border-left:4px solid var(--primary)}
h3{font-size:15px;margin:16px 0 8px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px}
.stat .v{font-size:22px;font-weight:680;line-height:1.2}
.stat .l{font-size:12px;color:var(--text-3);margin-top:2px}
.stat .v.up{color:var(--up)} .stat .v.down{color:var(--down)}
.bar-row{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:13px}
.bar-row .nm{width:96px;color:var(--text-2)}
.bar-row .track{flex:1;height:16px;background:var(--neutral-soft);border-radius:4px;overflow:hidden}
.bar-row .fill{height:100%;background:var(--primary)}
.bar-row .ct{width:52px;text-align:right;font-variant-numeric:tabular-nums}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0}
.toolbar input,.toolbar select{font-family:inherit;font-size:13px;padding:6px 10px;
  border:1px solid var(--border-strong);border-radius:var(--radius-sm);background:var(--surface);color:var(--text)}
.tbl-wrap{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);overflow:auto;max-height:620px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--border);text-align:left;white-space:nowrap}
th{background:var(--neutral-soft);font-weight:600;color:var(--text-2);font-size:12.5px;
  position:sticky;top:0;z-index:2;cursor:pointer}
tr:hover td{background:var(--primary-soft)}
td.num{font-variant-numeric:tabular-nums;text-align:right}
.pill{display:inline-block;font-size:11.5px;padding:2px 8px;border-radius:99px;font-weight:600}
.pill.up{background:var(--up-soft);color:var(--up)}
.pill.down{background:var(--down-soft);color:var(--down)}
.pill.div{background:var(--warn-soft);color:var(--warn)}
.pill.none{background:var(--neutral-soft);color:var(--text-2)}
.pill.ok{background:var(--down-soft);color:var(--down)}
.pill.bad{background:var(--warn-soft);color:var(--warn)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px 20px;margin-bottom:14px}
.card .hd{display:flex;justify-content:space-between;align-items:baseline;
  flex-wrap:wrap;gap:8px;border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:12px}
.card .hd .t{font-size:16px;font-weight:650}
.card .hd .t small{font-weight:400;color:var(--text-3);font-size:12.5px;margin-left:8px}
.dims{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:10px;margin:10px 0}
.dim{border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px}
.dim .n{font-size:12px;color:var(--text-3)}
.dim .s{font-size:15px;font-weight:650}
.dim .track{height:6px;background:var(--neutral-soft);border-radius:3px;margin-top:6px;overflow:hidden}
.dim .track i{display:block;height:100%;background:var(--primary)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.kv{font-size:13px}
.kv div{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed var(--border)}
.kv div:last-child{border-bottom:none}
.kv b{font-weight:600;color:var(--text-2);font-size:12.5px}
code{font-family:var(--mono);font-size:12px;background:var(--neutral-soft);padding:1px 5px;border-radius:4px}
.note{background:var(--warn-soft);border-left:4px solid var(--warn);border-radius:var(--radius-sm);
  padding:12px 14px;font-size:13px;margin:12px 0}
.note.ok{background:var(--down-soft);border-left-color:var(--down)}
footer{margin-top:34px;padding-top:14px;border-top:1px solid var(--border);
  color:var(--text-3);font-size:12.5px;text-align:center}
.sc{font-size:12.5px;color:var(--text-2)}
"""

SORT_JS = """
document.querySelectorAll('th[data-k]').forEach(function(th){
  th.addEventListener('click',function(){
    var tb=th.closest('table').tBodies[0]; var k=+th.dataset.k; var asc=th.dataset.asc!=='1';
    th.dataset.asc=asc?'1':'0';
    Array.prototype.slice.call(tb.rows).sort(function(a,b){
      var x=a.cells[k].dataset.v!==undefined?a.cells[k].dataset.v:a.cells[k].innerText;
      var y=b.cells[k].dataset.v!==undefined?b.cells[k].dataset.v:b.cells[k].innerText;
      var nx=parseFloat(x), ny=parseFloat(y);
      if(!isNaN(nx)&&!isNaN(ny)){return asc?nx-ny:ny-nx;}
      return asc?String(x).localeCompare(String(y)):String(y).localeCompare(String(x));
    }).forEach(function(r){tb.appendChild(r);});
  });
});
var q=document.getElementById('q');
if(q){q.addEventListener('input',function(){
  var v=q.value.trim().toLowerCase();
  document.querySelectorAll('#rank tbody tr').forEach(function(r){
    r.style.display=r.innerText.toLowerCase().indexOf(v)>=0?'':'none';});
});}
var f=document.getElementById('fconf');
if(f){f.addEventListener('change',function(){
  var v=f.value;
  document.querySelectorAll('#rank tbody tr').forEach(function(r){
    r.style.display=(!v||r.dataset.conf===v)?'':'none';});
});}
"""
