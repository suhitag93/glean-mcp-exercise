# Product Roadmap – H1 2025

**Document ID:** prod-roadmap-h1-2025  
**Category:** Product  
**Last Updated:** 2025-01-20  
**Owner:** Product Management

## Executive Summary

In H1 2025, Acme Corp will focus on three strategic themes: **AI-powered search**, **enterprise integrations**, and **platform performance**. These themes directly support our goal of increasing enterprise ARR by 40% and reducing customer churn below 5%.

## Theme 1: AI-Powered Search

### Q1 Deliverables

- **Semantic search (GA)**: Launch vector-based semantic search to all customers. Reduces "zero results" queries by an estimated 35%.
- **Search autocomplete v2**: Personalized suggestions based on user history and team context.
- **Query rewriting**: Automatic query expansion using synonym libraries.

### Q2 Deliverables

- **AI Answers**: Conversational answer synthesis over indexed documents (RAG-based). Available as beta to enterprise tier.
- **Multi-language search**: Support for 12 additional languages (Spanish, French, German, Japanese, Korean, Portuguese, Italian, Dutch, Polish, Swedish, Turkish, Arabic).
- **Image search**: Search within documents using visual similarity.

## Theme 2: Enterprise Integrations

### Q1 Deliverables

- **Salesforce connector (GA)**: Full bidirectional sync for Accounts, Contacts, Opportunities, and Cases.
- **SAP connector (beta)**: Index SAP HR and Finance data for enterprise customers.
- **Webhook v2**: Enhanced filtering, payload templates, and delivery guarantees.

### Q2 Deliverables

- **ServiceNow connector (GA)**: Index incident, problem, and change management records.
- **Custom connector SDK**: Allow customers to build their own connectors using a standardized Python SDK.
- **SCIM provisioning**: Automated user and group provisioning from Okta, Azure AD, and JumpCloud.

## Theme 3: Platform Performance

### Q1 Deliverables

- **Indexing throughput +3x**: Parallelized pipeline to handle 3x more document ingestion without impacting search latency.
- **p99 search latency <200ms**: Infrastructure improvements targeting sub-200ms p99 for cached queries.
- **Disaster recovery drills**: Monthly automated DR exercises with RTO target of 15 minutes.

### Q2 Deliverables

- **Multi-region support**: Data residency options for EU and APAC (SOC 2 and GDPR compliance).
- **Incremental indexing**: Support delta updates for large datasources to reduce re-indexing costs.
- **Query caching layer**: Redis-based semantic cache to reduce LLM inference costs by ~40%.

## Key Milestones

| Date | Milestone |
|---|---|
| Feb 3 | Semantic search GA launch |
| Mar 14 | Salesforce connector GA |
| Apr 1 | AI Answers beta launch |
| May 15 | Multi-region EU data residency available |
| Jun 30 | H1 OKR review and H2 planning kickoff |

## Dependencies and Risks

- **AI Answers**: Depends on LLM provider capacity; have fallback to open-source models (Llama 3.1) if capacity is constrained.
- **Multi-region**: Requires data migration tooling not yet scoped; risk of Q2 slip.
- **SAP connector**: Enterprise customer pilot dependent on SAP providing beta API access by Jan 31.

## Contact

For roadmap questions, contact the Product team at product@acme-corp.example.com or Slack #product-roadmap.
