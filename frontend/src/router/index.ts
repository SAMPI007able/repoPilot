import { createRouter, createWebHistory } from 'vue-router'
import Home from '../pages/Home.vue'
import SignIn from '../pages/SignIn.vue'
import AuthCallback from '../pages/AuthCallback.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home,
      meta: { requiresAuth: true },
    },
    { path: '/sign-in', name: 'sign-in', component: SignIn, meta: { public: true } },
    { path: '/auth/callback', name: 'auth-callback', component: AuthCallback, meta: { public: true } },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export default router
