# Release Process

Sample release process, in this example we're releasing `0.5.0`.

1. **Update version**
   ```bash
   sed -i '' 's/version=.*/version="0.5.0",/' setup.py
   ```

2. **Commit and push**
   ```bash
   git add setup.py
   git commit -m "Release 0.5.0"
   git push origin main
   ```

3. **Create and push tag**
   ```bash
   git tag 0.5.0
   git push origin 0.5.0
   ```

4. **GitHub Actions will automatically**
   - Build the distribution
   - Publish to PyPI (on tag push)
   - Publish to TestPyPI
   - Create GitHub release with signed artifacts