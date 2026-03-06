# Engineering Module - Standard Operating Procedures (SOP)

## Purpose
Defines the standard API and process flow for route card, drawing/document, and engineering change management with traceability and validation controls.
# Engineering Module - Standard Operating Procedures (SOP)

## 1. Route Card Management
- Create, edit, and release route cards for each job or batch.
- Ensure all required process steps and quality checks are included.
- Route cards must be approved before use in production.
- Obsolete route cards when superseded, but retain for traceability.

## 2. Drawing/Document Management
- Upload and version control all engineering drawings and documents.
- Link documents to relevant jobs, parts, or route cards.
- Restrict editing to authorized users only.

## 3. Engineering Change Requests (ECR)
- Submit ECRs for any process, design, or document change.
- Review and approve ECRs with cross-functional team.
- Update affected route cards and documents after approval.

## 4. Traceability
- Maintain audit logs for all changes to route cards and documents.
- Link route cards to production batches and quality records.
- Ensure all changes are reviewable and reversible.

## Preconditions
- Authenticated user with Engineering or Admin role.
- Job or batch must exist for route card creation.

## Standard Flow
1. **Route Card Management**
	- Create: `POST /api/v1/engineering/route-card` (job/batch, process steps, quality checks)
	- Edit: `PATCH /api/v1/engineering/route-card/{id}`
	- Approve/Release: `POST /api/v1/engineering/route-card/{id}/approve`
	- Obsolete: `PATCH /api/v1/engineering/route-card/{id}/obsolete` (retained for traceability)
2. **Drawing/Document Management**
	- Upload: `POST /api/v1/engineering/document/upload` (file, metadata)
	- Version: `POST /api/v1/engineering/document/{id}/version`
	- Link: `POST /api/v1/engineering/document/{id}/link` (job/part/route card)
	- Edit restricted to authorized users
3. **Engineering Change Requests (ECR)**
	- Submit: `POST /api/v1/engineering/ecr` (change details)
	- Review/Approve: `POST /api/v1/engineering/ecr/{id}/approve`
	- Update affected route cards/documents after approval

## Control Rules
- Only authorized users can edit or approve route cards/documents.
- Obsoleted route cards are retained for traceability.
- ECRs require cross-functional approval before implementation.
- All changes are audit-logged.

## Validation Checklist
- Route card creation rejects missing process steps or quality checks.
- Document upload rejects missing metadata or invalid file types.
- ECR submission requires detailed change description.
- Approval actions require proper authorization.

## Traceability & Audit
- All changes to route cards, documents, and ECRs are logged with user, timestamp, and action.
- Route cards are linked to production batches and quality records.
- All changes are reviewable and reversible for compliance.
