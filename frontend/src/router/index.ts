import { createRouter, createWebHistory } from 'vue-router'
import Home from '../pages/Home.vue'
import Workspace from '../pages/Workspace.vue'
import Generate from '../pages/Generate.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home,
    },
    {
      path: '/workspace',
      name: 'workspace',
      component: Workspace,
    },
    {
      path: '/generate',
      name: 'generate',
      component: Generate,
    },
  ],
})

export default router
