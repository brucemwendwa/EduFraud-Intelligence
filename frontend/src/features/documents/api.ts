import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from '@/api/schema';
import type { ApplicationDocument, DocumentDownload, DocumentReview } from '@/api/types';
import { api } from '@/lib/api';

type S = components['schemas'];

/** Browser-facing multipart payloads retain the generated category type and use File at the boundary. */
export type StudentDocumentUpload = Omit<
  S['Body_upload_document_api_v1_student_applications__application_id__documents_post'],
  'file'
> & { file: File };

export type StudentDocumentReplacement = Omit<
  S['Body_replace_document_api_v1_student_documents__document_id__replace_post'],
  'file'
> & { file: File };

export type ReplaceStudentDocumentInput = StudentDocumentReplacement & {
  applicationId: string;
  documentId: string;
};

export type ReviewDocumentInput = DocumentReview & {
  applicationId: string;
  documentId: string;
};

export const documentKeys = {
  all: ['documents'] as const,
  student: (applicationId: string) => ['documents', 'student', applicationId] as const,
  staff: (applicationId: string) => ['documents', 'staff', applicationId] as const,
};

const hasActiveScan = (documents: ApplicationDocument[] | undefined) =>
  documents?.some((document) => document.status === 'pending_scan' || document.status === 'scanning') ?? false;

function documentFormData({ category, file }: StudentDocumentUpload | StudentDocumentReplacement) {
  const form = new FormData();
  form.append('category', category);
  form.append('file', file);
  return form;
}

export async function listStudentDocuments(applicationId: string): Promise<ApplicationDocument[]> {
  return (await api.get<ApplicationDocument[]>(`/student-applications/${applicationId}/documents`)).data;
}

export async function uploadStudentDocument(
  applicationId: string,
  body: StudentDocumentUpload,
): Promise<ApplicationDocument> {
  return (await api.post<ApplicationDocument>(`/student-applications/${applicationId}/documents`, documentFormData(body))).data;
}

export async function replaceStudentDocument(
  documentId: string,
  body: StudentDocumentReplacement,
): Promise<ApplicationDocument> {
  return (await api.post<ApplicationDocument>(`/student-documents/${documentId}/replace`, documentFormData(body))).data;
}

export async function requestStudentDocumentDownload(documentId: string): Promise<DocumentDownload> {
  return (await api.post<DocumentDownload>(`/student-documents/${documentId}/download`)).data;
}

export async function listStaffDocuments(applicationId: string): Promise<ApplicationDocument[]> {
  return (await api.get<ApplicationDocument[]>(`/applications/${applicationId}/documents`)).data;
}

export async function requestStaffDocumentDownload(documentId: string): Promise<DocumentDownload> {
  return (await api.post<DocumentDownload>(`/documents/${documentId}/download`)).data;
}

export async function reviewDocument(documentId: string, body: DocumentReview): Promise<ApplicationDocument> {
  return (await api.patch<ApplicationDocument>(`/documents/${documentId}/review`, body)).data;
}

function invalidateDocumentLists(queryClient: ReturnType<typeof useQueryClient>, applicationId: string) {
  void queryClient.invalidateQueries({ queryKey: documentKeys.student(applicationId) });
  void queryClient.invalidateQueries({ queryKey: documentKeys.staff(applicationId) });
}

export function useStudentDocuments(applicationId: string | undefined) {
  return useQuery({
    queryKey: documentKeys.student(applicationId ?? ''),
    queryFn: () => listStudentDocuments(applicationId!),
    enabled: Boolean(applicationId),
    refetchInterval: (query) => (hasActiveScan(query.state.data) ? 5_000 : false),
  });
}

export function useStudentDocumentUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, ...body }: StudentDocumentUpload & { applicationId: string }) =>
      uploadStudentDocument(applicationId, body),
    onSuccess: (_document, { applicationId }) => invalidateDocumentLists(queryClient, applicationId),
  });
}

export function useStudentDocumentReplacement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId: _applicationId, documentId, ...body }: ReplaceStudentDocumentInput) =>
      replaceStudentDocument(documentId, body),
    onSuccess: (_document, { applicationId }) => invalidateDocumentLists(queryClient, applicationId),
  });
}

export function useStaffDocuments(applicationId: string | undefined) {
  return useQuery({
    queryKey: documentKeys.staff(applicationId ?? ''),
    queryFn: () => listStaffDocuments(applicationId!),
    enabled: Boolean(applicationId),
  });
}

export function useReviewDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId: _applicationId, documentId, ...body }: ReviewDocumentInput) =>
      reviewDocument(documentId, body),
    onSuccess: (_document, { applicationId }) => invalidateDocumentLists(queryClient, applicationId),
  });
}
