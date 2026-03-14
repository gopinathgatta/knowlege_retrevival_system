import win32com.client
import os

try:
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False

    # absolute paths
    front_page = os.path.abspath("Front Page.docx")
    report = os.path.abspath("B16_Complete.docx")
    output_pdf = os.path.abspath("B16.pdf")
    output_docx = os.path.abspath("B16_Combined.docx")
    
    # Check if files exist
    if not os.path.exists(front_page) or not os.path.exists(report):
        print(f"Error: Required files not found. Front Page: {os.path.exists(front_page)}, Report: {os.path.exists(report)}")
        word.Quit()
        exit(1)

    print("Opening Front Page.docx...")
    # open front page
    doc = word.Documents.Open(front_page)
    
    print("Merging B16_Final.docx...")
    # Go to end of document
    word.Selection.EndKey(Unit=6) # 6=wdStory
    # Insert page break
    word.Selection.InsertBreak(Type=7) # 7=wdPageBreak
    
    # Insert the main report
    word.Selection.InsertFile(FileName=report)
    
    print("Updating Table of Contents...")
    # Try updating fields (specifically Table of Contents)
    doc.TablesOfContents(1).Update() if doc.TablesOfContents.Count > 0 else word.ActiveDocument.Fields.Update()
    
    print("Saving as PDF...")
    # Save as pdf
    doc.SaveAs(output_pdf, FileFormat=17) # 17=wdFormatPDF
    
    # Optionally save as docx just in case
    doc.SaveAs(output_docx)
    
    doc.Close(False)
    word.Quit()
    print(f"Successfully created PDF: {output_pdf}")

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Failed: {str(e)}")
    try:
        word.Quit()
    except:
        pass
