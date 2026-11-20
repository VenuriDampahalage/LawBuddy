import { Route, Routes } from 'react-router-dom'

import RequireAuth from './components/RequireAuth'
import SiteLayout from './components/SiteLayout'
import Account from './pages/Account'
import AdminAmendments from './pages/admin/Amendments'
import AdminLayout from './pages/admin/AdminLayout'
import AdminDocuments from './pages/admin/Documents'
import AdminFeedback from './pages/admin/Feedback'
import AdminUsers from './pages/admin/Users'
import Chat from './pages/Chat'
import Home from './pages/Home'
import { Privacy, Terms } from './pages/Legal'
import Login from './pages/Login'
import NotFound from './pages/NotFound'
import Register from './pages/Register'

export default function App() {
  return (
    <Routes>
      {/* Chat has its own full-screen layout (sidebar + conversation), no site navbar/footer. */}
      <Route path="chat/:conversationId?" element={<RequireAuth><Chat /></RequireAuth>} />
      <Route element={<SiteLayout />}>
        <Route index element={<Home />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="account" element={<RequireAuth><Account /></RequireAuth>} />
        <Route path="admin" element={<RequireAuth admin><AdminLayout /></RequireAuth>}>
          <Route index element={<AdminDocuments />} />
          <Route path="amendments" element={<AdminAmendments />} />
          <Route path="users" element={<AdminUsers />} />
          <Route path="feedback" element={<AdminFeedback />} />
        </Route>
        <Route path="privacy" element={<Privacy />} />
        <Route path="terms" element={<Terms />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
