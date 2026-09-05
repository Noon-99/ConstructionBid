"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api, ApiError } from "@/lib/api";
import { Upload, FileText, AlertCircle, List } from "lucide-react";
import Link from "next/link";

export default function HomePage() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentProjects, setRecentProjects] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Load recent projects from localStorage
    const stored = localStorage.getItem("recentProjects");
    if (stored) {
      try {
        setRecentProjects(JSON.parse(stored));
      } catch (e) {
        console.error("Failed to parse recent projects:", e);
      }
    }
  }, []);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please upload a PDF file");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      // Step 1: Upload PDF
      const uploadResult = await api.uploadPdf(file);
      const projectId = uploadResult.project_id;
      
      // Step 2: Pipeline is auto-triggered by backend on upload
      // (No need to call api.runProject - backend does it automatically)
      
      // Step 3: Add to recent projects
      const updated = [projectId, ...recentProjects.filter(id => id !== projectId)].slice(0, 10);
      setRecentProjects(updated);
      localStorage.setItem("recentProjects", JSON.stringify(updated));

      // Step 4: Navigate to project page (will show progress automatically)
      window.location.href = `/projects/${projectId}`;
    } catch (err) {
      console.error("Upload error:", err);
      if (err instanceof ApiError) {
        // Show the actual backend error message
        const errorMsg = err.message || err.response?.detail || `Upload failed: ${err.status}`;
        setError(errorMsg);
      } else if (err instanceof Error) {
        // Network errors, CORS, etc.
        setError(`Network error: ${err.message}. Is the backend running at ${process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/v1"}?`);
      } else {
        setError("Failed to upload file. Please check the browser console for details.");
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      <div className="container mx-auto px-4 py-16">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h1 className="text-4xl font-bold text-gray-900 mb-4">
              Construction Bid AI
            </h1>
            <p className="text-xl text-gray-600 mb-4">
              Upload construction drawings to generate automated bid proposals
            </p>
            <Link href="/projects">
              <Button variant="outline">
                <List className="h-4 w-4 mr-2" />
                View All Projects
              </Button>
            </Link>
          </div>

          <Card className="mb-8">
            <CardHeader>
              <CardTitle>Upload PDF</CardTitle>
              <CardDescription>
                Upload a construction drawing PDF to start processing
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col items-center gap-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={handleFileUpload}
                  disabled={uploading}
                  className="hidden"
                />
                <Button 
                  disabled={uploading} 
                  size="lg" 
                  className="w-full sm:w-auto"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="mr-2 h-4 w-4" />
                  {uploading ? "Uploading..." : "Choose PDF File"}
                </Button>
                {error && (
                  <Alert variant="destructive" className="w-full">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}
              </div>
            </CardContent>
          </Card>

          {recentProjects.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Recent Projects</CardTitle>
                <CardDescription>
                  View previously processed projects
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {recentProjects.map((projectId) => (
                    <Link
                      key={projectId}
                      href={`/projects/${projectId}`}
                      className="block p-3 border rounded-lg hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-gray-500" />
                          <span className="font-mono text-sm">{projectId}</span>
                        </div>
                        <Badge variant="outline">View</Badge>
                      </div>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
