// 生图结果曾以设置里 base_url 指向的上游域名(如 chatgpt.com)落库,浏览器通常无法
// 直接访问;每张图在本服务 /images/ 下都有同源副本,这里把此类链接统一改写为同源地址。
export function toLocalImageUrl(url: string) {
  const marker = "/images/";
  const index = url.indexOf(marker);
  return index < 0 ? url : `/images/${url.slice(index + marker.length)}`;
}
