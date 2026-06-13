// Service Worker - 离线缓存策略
const CACHE_NAME = 'taiji-agi-v3.2'
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/assets/index.js',
  '/assets/index.css',
]

// 安装时预缓存静态资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE)
    })
  )
})

// 激活时清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName)
          }
        })
      )
    })
  )
})

// 网络优先 + 缓存回退策略
self.addEventListener('fetch', (event) => {
  // API 请求：网络优先
  if (event.request.url.includes('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // 缓存成功的 GET 请求
          if (event.request.method === 'GET' && response.status === 200) {
            const responseClone = response.clone()
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone)
            })
          }
          return response
        })
        .catch(() => {
          // 网络失败，尝试从缓存返回
          return caches.match(event.request)
        })
    )
    return
  }

  // 静态资源：缓存优先
  event.respondWith(
    caches.match(event.request).then((response) => {
      return (
        response ||
        fetch(event.request).then((fetchResponse) => {
          // 缓存新资源
          if (fetchResponse.status === 200) {
            const responseClone = fetchResponse.clone()
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone)
            })
          }
          return fetchResponse
        })
      )
    })
  )
})
