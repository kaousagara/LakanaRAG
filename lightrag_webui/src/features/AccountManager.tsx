import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getAccounts, createAccount, deleteAccount, updateAccount, Account } from '@/api/lightrag'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { Table, TableHead, TableHeader, TableRow, TableCell, TableBody } from '@/components/ui/Table'

export default function AccountManager() {
  const { t } = useTranslation()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('user')

  const loadAccounts = async () => {
    try {
      const data = await getAccounts()
      setAccounts(data)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => { loadAccounts() }, [])

  const handleCreate = async () => {
    if (!username || !password) return
    await createAccount({ username, password, role, active: true })
    setUsername('')
    setPassword('')
    loadAccounts()
  }

  const handleToggle = async (acc: Account) => {
    await updateAccount(acc.username, { active: !acc.active })
    loadAccounts()
  }

  const handleDelete = async (acc: Account) => {
    await deleteAccount(acc.username)
    loadAccounts()
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex gap-2">
        <Input value={username} onChange={e => setUsername(e.target.value)} placeholder={t('accountManager.username')} />
        <Input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder={t('accountManager.password')} />
        <select value={role} onChange={e => setRole(e.target.value)} className="border rounded px-2">
          <option value="user">User</option>
          <option value="admin">Admin</option>
        </select>
        <Button onClick={handleCreate}>{t('accountManager.create')}</Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('accountManager.username')}</TableHead>
            <TableHead>{t('accountManager.role')}</TableHead>
            <TableHead>{t('accountManager.active')}</TableHead>
            <TableHead></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {accounts.map(acc => (
            <TableRow key={acc.username}>
              <TableCell>{acc.username}</TableCell>
              <TableCell>{acc.role}</TableCell>
              <TableCell>
                <input type="checkbox" checked={acc.active} onChange={() => handleToggle(acc)} />
              </TableCell>
              <TableCell>
                <Button variant="destructive" size="sm" onClick={() => handleDelete(acc)}>{t('accountManager.delete')}</Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
