// Command find_overexported lists top-level exported names that no other package of a module
// uses, so each can be unexported.
//
// A name counts as used when a file of another package — an external test package included —
// selects it through an import of the declaring package, or dot-imports that package, or when it
// appears in the declaration of a name that is used: the result type of a used function, a field
// type of a used struct, a parameter of a used type's exported method. Methods, struct fields,
// generated files, declarations in _test.go files and functions marked //export are not
// candidates.
//
// Usage:
//
//	go run find_overexported.go ROOT
//
// ROOT must contain a go.mod. Nested modules under ROOT are skipped. The script needs Go 1.21 or
// later and nothing outside the standard library.
//
// Exit codes: 0 nothing found, 1 names found, 2 ROOT is not a module or a file does not parse.
package main

import (
	"cmp"
	"errors"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
)

const (
	exitClean = 0
	exitFound = 1
	exitError = 2
)

var (
	errNoModule = errors.New("no module directive in go.mod")
	errUsage    = errors.New("usage: go run find_overexported.go ROOT")
)

// declaration is one exported top-level name and where it is declared.
type declaration struct {
	importPath string
	name       string
	kind       string
	position   token.Position
}

// packageFiles holds the parsed files of one directory, split by package clause.
type packageFiles struct {
	importPath string
	name       string
	files      []*ast.File // the package itself, including its internal _test.go files
	external   []*ast.File // files of the external test package, name_test
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) != 1 {
		return reportError(stderr, errUsage)
	}
	root := args[0]

	modulePath, err := readModulePath(filepath.Join(root, "go.mod"))
	if err != nil {
		return reportError(stderr, err)
	}
	fileSet := token.NewFileSet()
	packages, err := parseModule(fileSet, root, modulePath)
	if err != nil {
		return reportError(stderr, err)
	}

	unused := findUnused(fileSet, packages)
	for _, d := range unused {
		_, err := fmt.Fprintf(stdout, "%s: %s %s is exported but not used outside %s\n",
			d.position, d.kind, d.name, d.importPath)
		if err != nil {
			return reportError(stderr, fmt.Errorf("write report: %w", err))
		}
	}
	if len(unused) > 0 {
		return exitFound
	}
	return exitClean
}

// reportError writes a diagnostic and returns its exit code; a failed write to stderr leaves
// nowhere to report that failure.
func reportError(stderr io.Writer, err error) int {
	_, _ = fmt.Fprintf(stderr, "find_overexported: %v\n", err)
	return exitError
}

func readModulePath(goModPath string) (string, error) {
	content, err := os.ReadFile(goModPath) //nolint:gosec // reading the module the caller named is the job
	if err != nil {
		return "", fmt.Errorf("read module path: %w", err)
	}
	for _, line := range strings.Split(string(content), "\n") { //nolint:modernize // runs on Go 1.21, before SplitSeq
		rest, found := strings.CutPrefix(strings.TrimSpace(line), "module")
		if !found {
			continue
		}
		modulePath := strings.TrimSpace(rest)
		if unquoted, err := strconv.Unquote(modulePath); err == nil {
			modulePath = unquoted
		}
		return modulePath, nil
	}
	return "", fmt.Errorf("%s: %w", goModPath, errNoModule)
}

func parseModule(fileSet *token.FileSet, root, modulePath string) (map[string]*packageFiles, error) {
	packages := make(map[string]*packageFiles)
	walk := func(filePath string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return skipDirectory(root, filePath, entry)
		}
		if filepath.Ext(filePath) != ".go" {
			return nil
		}

		file, err := parser.ParseFile(fileSet, filePath, nil, parser.ParseComments|parser.SkipObjectResolution)
		if err != nil {
			return fmt.Errorf("parse %s: %w", filePath, err)
		}
		relativeDir, err := filepath.Rel(root, filepath.Dir(filePath))
		if err != nil {
			return fmt.Errorf("locate %s: %w", filePath, err)
		}
		importPath := path.Join(modulePath, filepath.ToSlash(relativeDir))
		files, ok := packages[importPath]
		if !ok {
			files = &packageFiles{importPath: importPath}
			packages[importPath] = files
		}
		packageName := file.Name.Name
		if strings.HasSuffix(packageName, "_test") && strings.HasSuffix(filePath, "_test.go") {
			files.external = append(files.external, file)
			return nil
		}
		files.name = packageName
		files.files = append(files.files, file)
		return nil
	}
	if err := filepath.WalkDir(root, walk); err != nil { //nolint:gosec // walking the tree the caller named is the job
		return nil, fmt.Errorf("walk %s: %w", root, err)
	}
	return packages, nil
}

// skipDirectory reports fs.SkipDir for directories the go command ignores and for nested modules.
func skipDirectory(root, dirPath string, entry fs.DirEntry) error {
	if dirPath == root {
		return nil
	}
	name := entry.Name()
	if name == "vendor" || name == "testdata" || strings.HasPrefix(name, ".") || strings.HasPrefix(name, "_") {
		return fs.SkipDir
	}
	if _, err := os.Stat(filepath.Join(dirPath, "go.mod")); err == nil {
		return fs.SkipDir
	}
	return nil
}

func findUnused(fileSet *token.FileSet, packages map[string]*packageFiles) []declaration {
	used := collectUses(packages)
	for _, files := range packages {
		markSignatureTypes(files, used)
	}

	var unused []declaration
	for _, files := range packages {
		for _, file := range files.files {
			if isCandidateFile(fileSet, file) {
				for _, d := range exportedDeclarations(fileSet, files.importPath, file) {
					if !used[d.importPath+"."+d.name] && !used[d.importPath+".*"] {
						unused = append(unused, d)
					}
				}
			}
		}
	}
	slices.SortFunc(unused, func(a, b declaration) int {
		return cmp.Or(
			cmp.Compare(a.position.Filename, b.position.Filename),
			cmp.Compare(a.position.Line, b.position.Line),
		)
	})
	return unused
}

func isCandidateFile(fileSet *token.FileSet, file *ast.File) bool {
	fileName := fileSet.Position(file.Package).Filename
	return !strings.HasSuffix(fileName, "_test.go") && !ast.IsGenerated(file)
}

// collectUses returns the set of "importPath.Name" selected from outside the declaring package,
// with "importPath.*" for a dot import.
func collectUses(packages map[string]*packageFiles) map[string]bool {
	nameByImportPath := make(map[string]string, len(packages))
	for importPath, files := range packages {
		nameByImportPath[importPath] = files.name
	}

	used := make(map[string]bool)
	for importPath, files := range packages {
		for _, file := range files.files {
			recordUses(file, importPath, nameByImportPath, used)
		}
		for _, file := range files.external {
			recordUses(file, "", nameByImportPath, used)
		}
	}
	return used
}

func recordUses(file *ast.File, ownImportPath string, nameByImportPath map[string]string, used map[string]bool) {
	importPathByLocalName := make(map[string]string)
	for _, spec := range file.Imports {
		importPath, err := strconv.Unquote(spec.Path.Value)
		if err != nil || importPath == ownImportPath {
			continue
		}
		packageName, isModulePackage := nameByImportPath[importPath]
		if !isModulePackage {
			continue
		}
		localName := packageName
		if spec.Name != nil {
			localName = spec.Name.Name
		}
		if localName == "." {
			used[importPath+".*"] = true
			continue
		}
		importPathByLocalName[localName] = importPath
	}

	ast.Inspect(file, func(node ast.Node) bool {
		selector, ok := node.(*ast.SelectorExpr)
		if !ok {
			return true
		}
		qualifier, ok := selector.X.(*ast.Ident)
		if !ok {
			return true
		}
		if importPath, ok := importPathByLocalName[qualifier.Name]; ok {
			used[importPath+"."+selector.Sel.Name] = true
		}
		return true
	})
}

// markSignatureTypes marks as used every exported name of the package that appears in the
// declaration of a used one, repeating until nothing new is marked.
func markSignatureTypes(files *packageFiles, used map[string]bool) {
	referencesByName := make(map[string][]string)
	for _, file := range files.files {
		for _, decl := range file.Decls {
			for _, reference := range declarationTypes(decl) {
				referencesByName[reference.name] = append(referencesByName[reference.name],
					exportedIdentifiers(reference.expression)...)
			}
		}
	}

	for changed := true; changed; {
		changed = false
		for name, references := range referencesByName {
			if !used[files.importPath+"."+name] {
				continue
			}
			for _, reference := range references {
				key := files.importPath + "." + reference
				if !used[key] {
					used[key] = true
					changed = true
				}
			}
		}
	}
}

// typeReference ties a declared name to a type expression its users see.
type typeReference struct {
	name       string
	expression ast.Node
}

// declarationTypes returns the type expressions callers of each declared name see: a function's
// signature, a variable's type, a type's definition, and an exported method's signature filed
// under its receiver's type name.
func declarationTypes(decl ast.Decl) []typeReference {
	var references []typeReference
	switch d := decl.(type) {
	case *ast.FuncDecl:
		if d.Recv == nil {
			references = append(references, typeReference{name: d.Name.Name, expression: d.Type})
		} else if receiver := receiverTypeName(d.Recv); receiver != "" && d.Name.IsExported() {
			references = append(references, typeReference{name: receiver, expression: d.Type})
		}
	case *ast.GenDecl:
		for _, spec := range d.Specs {
			switch s := spec.(type) {
			case *ast.TypeSpec:
				references = append(references, typeReference{name: s.Name.Name, expression: s.Type})
			case *ast.ValueSpec:
				for _, name := range s.Names {
					if s.Type != nil {
						references = append(references, typeReference{name: name.Name, expression: s.Type})
					}
				}
			}
		}
	}
	return references
}

func receiverTypeName(receivers *ast.FieldList) string {
	if len(receivers.List) == 0 {
		return ""
	}
	expression := receivers.List[0].Type
	for {
		switch e := expression.(type) {
		case *ast.StarExpr:
			expression = e.X
		case *ast.IndexExpr:
			expression = e.X
		case *ast.IndexListExpr:
			expression = e.X
		case *ast.Ident:
			return e.Name
		default:
			return ""
		}
	}
}

// exportedIdentifiers lists the unqualified exported identifiers inside a type expression.
func exportedIdentifiers(node ast.Node) []string {
	var names []string
	ast.Inspect(node, func(n ast.Node) bool {
		switch identifier := n.(type) {
		case *ast.SelectorExpr:
			return false // qualified by another package
		case *ast.Ident:
			if identifier.IsExported() {
				names = append(names, identifier.Name)
			}
		}
		return true
	})
	return names
}

func exportedDeclarations(fileSet *token.FileSet, importPath string, file *ast.File) []declaration {
	var declarations []declaration
	add := func(name *ast.Ident, kind string) {
		if name.IsExported() {
			declarations = append(declarations, declaration{
				importPath: importPath,
				name:       name.Name,
				kind:       kind,
				position:   fileSet.Position(name.Pos()),
			})
		}
	}

	for _, decl := range file.Decls {
		switch d := decl.(type) {
		case *ast.FuncDecl:
			if d.Recv == nil && !isCgoExport(d) {
				add(d.Name, "func")
			}
		case *ast.GenDecl:
			for _, spec := range d.Specs {
				switch s := spec.(type) {
				case *ast.TypeSpec:
					add(s.Name, "type")
				case *ast.ValueSpec:
					for _, name := range s.Names {
						add(name, strings.ToLower(d.Tok.String()))
					}
				}
			}
		}
	}
	return declarations
}

func isCgoExport(function *ast.FuncDecl) bool {
	if function.Doc == nil {
		return false
	}
	return slices.ContainsFunc(function.Doc.List, func(comment *ast.Comment) bool {
		return strings.HasPrefix(comment.Text, "//export ")
	})
}
