export interface Scholarship {
    scholarship_code: string;
    title: string;
    link?: string;
    category?: string;
    education_system?: string[];
    tags?: string[];
    identity?: string[];
    amount_summary?: string;
    description?: string;
    application_date_text?: string;
    contact?: string;
    markdown_content?: string;
    created_at?: string;
}
export interface MetadataSchema {
    education_system: string[];
    tags: string[];
    identity: string[];
}
export type AdminMode = 'CREATE' | 'UPDATE';