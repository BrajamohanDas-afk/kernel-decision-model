"""Tiny live dashboard for the M2 pilot at http://localhost:8765 (stdlib only)."""
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE = Path(os.environ.get("WLP_LIVE", str(HERE / "live")))
PORT = 8765

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>WorkloadPilot - M2 pilot live</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
body{font-family:Segoe UI,Arial;margin:24px;background:#0f1420;color:#e8ecf3}
.card{background:#171e2e;border-radius:12px;padding:16px 20px;margin-bottom:16px}
h1{font-size:20px}.big{font-size:28px;font-weight:600}
.muted{color:#9aa7bd}.ok{color:#69d98c}.bad{color:#ff7b7b}
pre{white-space:pre-wrap;word-break:break-word;margin:0;font-size:12px}
</style></head><body>
<h1>WorkloadPilot &middot; M2 pilot &mdash; live</h1>
<div class="card"><div class="muted">status</div>
<div id="phase" class="big">&hellip;</div><div id="msg" class="muted">connecting&hellip;</div>
<div style="height:8px;background:#232c42;border-radius:4px;overflow:hidden;margin-top:8px">
<div id="progress" style="height:8px;background:#4f8cff;width:0%"></div></div></div>
<div class="card"><div class="muted">accuracy (heldout)</div>
<div>base: <span id="baseacc" class="bad">&mdash;</span>&nbsp;&nbsp;&rarr;&nbsp;&nbsp;tuned: <span id="tunedacc" class="ok">&mdash;</span></div></div>
<div class="card"><div class="muted">mid-training probe (per epoch, heldout)</div>
<div id="probeacc" class="big">&mdash;</div><pre id="probeclass">&mdash;</pre></div>
<div class="card"><div class="muted">training loss (per step)</div><canvas id="loss" height="90"></canvas></div>
<div class="card"><div class="muted">latest event</div><pre id="log">&mdash;</pre></div>
<script>
let chart=null;
async function tick(){
 try{
  const s=await (await fetch('/status.json?'+Date.now())).json();
  document.getElementById('phase').textContent=s.phase||'?';
  document.getElementById('msg').textContent=s.message||'';
  if(s.baseline&&s.baseline.accuracy!=null) document.getElementById('baseacc').textContent=(s.baseline.accuracy*100).toFixed(1)+'%';
  if(s.tuned&&s.tuned.accuracy!=null) document.getElementById('tunedacc').textContent=(s.tuned.accuracy*100).toFixed(1)+'%';
  const p=s.probe;
  if(p){
    document.getElementById('probeacc').textContent='epoch '+(p.epoch||'?')+' · acc '+(p.acc!=null?(p.acc*100).toFixed(1)+'%':'—')+' · macro-recall '+(p.macro_recall!=null?(p.macro_recall*100).toFixed(1)+'%':'—');
    document.getElementById('probeclass').textContent=Object.entries(p.per_class_recall||{}).map(function(kv){return kv[0]+': '+(kv[1]*100).toFixed(0)+'%';}).join('  |  ');
  }
  if(s.total_steps) document.getElementById('progress').style.width=Math.round(100*(s.step||0)/s.total_steps)+'%';
 }catch(e){}
 try{
  const text=await (await fetch('/metrics.jsonl?'+Date.now())).text();
  const rows=text.split('\\n').filter(x=>x.trim()).map(JSON.parse);
  const pts=rows.filter(r=>r.loss!=null).map(r=>({x:r.step,y:r.loss}));
  if(!chart){
    chart=new Chart(document.getElementById('loss'),{type:'line',
      data:{datasets:[{label:'loss',data:pts,borderColor:'#4f8cff',backgroundColor:'rgba(79,140,255,.15)',fill:true,pointRadius:0,tension:.25}]},
      options:{animation:false,scales:{x:{type:'linear',ticks:{color:'#9aa7bd'},grid:{color:'#232c42'}},y:{ticks:{color:'#9aa7bd'},grid:{color:'#232c42'}}}}});
  } else { chart.data.datasets[0].data=pts; chart.update('none'); }
  document.getElementById('log').textContent = rows.length ? JSON.stringify(rows[rows.length-1]) : '\\u2014';
 }catch(e){}
}
setInterval(tick,2000); tick();
</script></body></html>"""


def read_retry(path, default):
    for _ in range(5):  # Windows: the writer may be mid-swap; retry briefly
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return default
        except OSError:
            time.sleep(0.05)
    return default


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/status.json"):
            body = read_retry(LIVE / "status.json", b"{}")
            ctype = "application/json"
        elif self.path.startswith("/metrics.jsonl"):
            body = read_retry(LIVE / "metrics.jsonl", b"")
            ctype = "text/plain; charset=utf-8"
        else:
            body = PAGE.encode("utf-8")
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("dashboard: http://localhost:{}".format(PORT))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
