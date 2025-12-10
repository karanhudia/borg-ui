import { useParams } from 'react-router-dom'
import RepositoryForm from '../components/RepositoryForm'

export default function EditRepository() {
  const { id } = useParams<{ id: string }>()

  return <RepositoryForm mode="edit" repositoryId={id ? parseInt(id) : undefined} />
}
