// chatgpt.com sentinel 挑战程序的执行器（Turnstile 与 SO）。
//
// 移植自 chatgpt.com 前端 bundle 里的两套同构 VM（2026-10 版本，指令编号 0-35）。
// 挑战程序会读取真实页面里的 window/document/navigator 等属性，结果只在真正的
// chatgpt.com 页面上下文里才会被服务端接受，所以这段脚本通过 add_init_script
// 注入到常驻页面，由求解服务按需调用 window.__sentinelVM。
(() => {
  const xor = (text, key) => {
    let out = "";
    for (let i = 0; i < text.length; i++) out += String.fromCharCode(text.charCodeAt(i) ^ key.charCodeAt(i % key.length));
    return out;
  };

  function makeVM() {
    const Q = new Map();
    let steps = 0;

    async function run() {
      while (Q.get(9).length > 0) {
        const [op, ...args] = Q.get(9).shift();
        const result = Q.get(op)(...args);
        if (result && typeof result.then === "function") await result;
        steps++;
      }
    }

    function reset() {
      Q.clear();
      Q.set(0, (dx) => exec(dx, undefined, 60000));
      Q.set(1, (e, t) => Q.set(e, xor("" + Q.get(e), "" + Q.get(t))));
      Q.set(2, (e, t) => Q.set(e, t));
      Q.set(5, (e, t) => { const n = Q.get(e); Array.isArray(n) ? n.push(Q.get(t)) : Q.set(e, n + Q.get(t)); });
      Q.set(6, (e, t, n) => Q.set(e, Q.get(t)[Q.get(n)]));
      Q.set(7, (e, ...t) => Q.get(e)(...t.map((x) => Q.get(x))));
      Q.set(8, (e, t) => Q.set(e, Q.get(t)));
      Q.set(10, window);
      Q.set(11, (e, t) => Q.set(e, (Array.from(document.scripts || []).map((s) => s?.src?.match(Q.get(t))).filter((m) => m?.length)[0] ?? [])[0] ?? null));
      Q.set(12, (e) => Q.set(e, Q));
      Q.set(13, (e, t, ...n) => { try { Q.get(t)(...n); } catch (err) { Q.set(e, "" + err); } });
      Q.set(14, (e, t) => Q.set(e, JSON.parse("" + Q.get(t))));
      Q.set(15, (e, t) => Q.set(e, JSON.stringify(Q.get(t))));
      Q.set(17, (e, t, ...n) => {
        try {
          const r = Q.get(t)(...n.map((x) => Q.get(x)));
          if (r && typeof r.then === "function") return r.then((v) => { Q.set(e, v); }).catch((v) => { Q.set(e, "" + v); });
          Q.set(e, r);
        } catch (err) {
          Q.set(e, "" + err);
        }
      });
      Q.set(18, (e) => Q.set(e, atob("" + Q.get(e))));
      Q.set(19, (e) => Q.set(e, btoa("" + Q.get(e))));
      Q.set(20, (e, t, n, ...r) => (Q.get(e) === Q.get(t) ? Q.get(n)(...r) : null));
      Q.set(21, (e, t, n, r, ...i) => (Math.abs(Q.get(e) - Q.get(t)) > Q.get(n) ? Q.get(r)(...i) : null));
      Q.set(22, (e, t) => {
        const saved = [...Q.get(9)];
        Q.set(9, [...t]);
        return run().catch((v) => { Q.set(e, "" + v); }).finally(() => { Q.set(9, saved); });
      });
      Q.set(23, (e, t, ...n) => (Q.get(e) === void 0 ? null : Q.get(t)(...n)));
      Q.set(24, (e, t, n) => Q.set(e, Q.get(t)[Q.get(n)].bind(Q.get(t))));
      Q.set(25, () => {});
      Q.set(26, () => {});
      Q.set(27, (e, t) => { const n = Q.get(e); Array.isArray(n) ? n.splice(n.indexOf(Q.get(t)), 1) : Q.set(e, n - Q.get(t)); });
      Q.set(28, () => {});
      Q.set(29, (e, t, n) => Q.set(e, Q.get(t) < Q.get(n)));
      Q.set(33, (e, t, n) => Q.set(e, Number(Q.get(t)) * Number(Q.get(n))));
      Q.set(34, (e, t) => { try { return Promise.resolve(Q.get(t)).then((v) => { Q.set(e, v); }); } catch { return; } });
      Q.set(35, (e, t, n) => { const r = Number(Q.get(t)), i = Number(Q.get(n)); Q.set(e, i === 0 ? 0 : r / i); });
    }

    // key 为 undefined 时沿用上一次的状态（SO 的 snapshot 依赖 collector 留下的寄存器）。
    // softTimeout 对应前端 Turnstile 的行为：超时不报错，而是返回已执行步数。
    function exec(dx, key, timeoutMs, softTimeout) {
      return new Promise((resolve, reject) => {
        if (key !== undefined) {
          reset();
          steps = 0;
          Q.set(16, key);
        }
        let done = false;
        const timer = setTimeout(() => {
          if (done) return;
          done = true;
          softTimeout ? resolve("" + steps) : reject(new Error("vm_timeout"));
        }, timeoutMs);
        const ok = (v) => { if (!done) { done = true; clearTimeout(timer); resolve(v); } };
        const fail = (v) => { if (!done) { done = true; clearTimeout(timer); reject(v); } };
        Q.set(3, (v) => ok(btoa("" + v)));
        Q.set(4, (v) => fail(btoa("" + v)));
        Q.set(30, (e, t, n, r) => {
          const hasParams = Array.isArray(r);
          const params = hasParams ? n : [];
          const body = (hasParams ? r : n) || [];
          Q.set(e, (...args) => {
            if (done) return;
            const saved = [...Q.get(9)];
            if (hasParams) for (let i = 0; i < params.length; i++) Q.set(params[i], args[i]);
            Q.set(9, [...body]);
            return run().then(() => Q.get(t)).catch((v) => "" + v).finally(() => { Q.set(9, saved); });
          });
        });
        try {
          Q.set(9, JSON.parse(xor(atob(dx), "" + Q.get(16))));
          run().catch((v) => ok(btoa(steps + ": " + v)));
        } catch (err) {
          ok(btoa(steps + ": " + err));
        }
      });
    }

    return { exec };
  }

  window.__sentinelVM = {
    // key 是 chat-requirements/prepare 请求里提交的 p（requirements token）。
    turnstile: (dx, key) => makeVM().exec(dx, key, 500, true),
    so: async (collectorDx, snapshotDx, key) => {
      const vm = makeVM();
      await vm.exec(collectorDx, key, 60000);
      return vm.exec(snapshotDx, undefined, 60000);
    },
  };
})();
