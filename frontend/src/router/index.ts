import { createRouter, createWebHistory, START_LOCATION } from 'vue-router'
const Home = () => import('../pages/Home.vue')
const SignIn = () => import('../pages/SignIn.vue')
const AuthCallback = () => import('../pages/AuthCallback.vue')
const AdminPage = () => import('../pages/AdminPage.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home,
      meta: { public: true },
    },
    {
      path: '/repositories',
      name: 'repositories',
      component: Home,
      meta: { requiresAuth: true },
    },
    { path: '/sign-in', name: 'sign-in', component: SignIn, meta: { public: true } },
    { path: '/auth/callback', name: 'auth-callback', component: AuthCallback, meta: { public: true } },
    { path: '/admin', name: 'admin', component: AdminPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/support', name: 'support', component: () => import('../pages/SupportPage.vue'), meta: { requiresAuth: true } },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
  scrollBehavior(to, from, savedPosition) {
    // On a fresh load or reload, history.state still holds the last scroll position; always start
    // at the top instead. Saved positions are only restored for back/forward navigation.
    if (savedPosition && from !== START_LOCATION) return savedPosition
    if (to.hash) return { el: to.hash, top: 16, behavior: 'smooth' }
    return { top: 0 }
  },
})

export default router
