const statusText = document.getElementById("statusText");

async function boot() {
  const response = await fetch("/health");
  const health = await response.json();
  statusText.textContent = health.ok ? "服务已就绪" : "服务暂不可用";
}

boot().catch(() => {
  statusText.textContent = "服务连接失败";
});
