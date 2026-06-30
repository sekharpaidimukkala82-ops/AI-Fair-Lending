import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import toast from 'react-hot-toast'
import { Scale } from 'lucide-react'

export default function RegisterPage() {
  const [form, setForm] = useState({
    email: '',
    username: '',
    password: '',
    full_name: '',
    institution: '',
    role: 'analyst',
  })
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const mutation = useMutation({
    mutationFn: async (data: typeof form) => (await api.post('/auth/register', data)).data,
    onSuccess: (data) => {
      setAuth(
        { id: data.user_id, email: form.email, username: data.username, full_name: data.full_name, role: data.role, institution: data.institution },
        data.access_token
      )
      toast.success('Account created successfully!')
      navigate('/')
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Registration failed'),
  })

  const set = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(prev => ({ ...prev, [field]: e.target.value }))

  return (
    <div className="min-h-screen bg-gradient-to-br from-navy-900 to-blue-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="w-12 h-12 bg-blue-500 rounded-xl flex items-center justify-center">
              <Scale className="w-7 h-7 text-white" />
            </div>
            <div className="text-white text-2xl font-bold">FairLend AI</div>
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-6">Create Account</h2>
          <form onSubmit={e => { e.preventDefault(); mutation.mutate(form) }} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
                <input className="input" placeholder="Jane Smith" value={form.full_name} onChange={set('full_name')} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Username *</label>
                <input className="input" placeholder="jsmith" required value={form.username} onChange={set('username')} />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
              <input className="input" type="email" required value={form.email} onChange={set('email')} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password * (min 8 chars)</label>
              <input className="input" type="password" required minLength={8} value={form.password} onChange={set('password')} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Institution</label>
              <input className="input" placeholder="First National Bank" value={form.institution} onChange={set('institution')} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select className="input" value={form.role} onChange={set('role')}>
                <option value="analyst">Fair Lending Analyst</option>
                <option value="auditor">Compliance Auditor (Read-only)</option>
              </select>
            </div>
            <button type="submit" disabled={mutation.isPending} className="btn-primary w-full py-3">
              {mutation.isPending ? 'Creating account…' : 'Create Account'}
            </button>
          </form>
          <p className="text-center text-sm text-gray-500 mt-4">
            Already have an account?{' '}
            <Link to="/login" className="text-navy-900 font-medium hover:underline">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
