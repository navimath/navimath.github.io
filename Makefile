.PHONY: website

website:
	pandoc --standalone \
         --from commonmark_x+alerts \
         --output=website/index.html \
         --template=pandoc/template.html4 \
         --css=style.css \
         --toc \
         --toc-depth=1 \
         --resource-path=. \
         --lua-filter=pandoc/paper.lua \
         --lua-filter=pandoc/date.lua \
         src/index.md


movies:
	mkdir -p website

	pandoc \
		--standalone \
		--from commonmark_x+alerts \
		--output=website/movies.html \
		--template=pandoc/mediareview.html4 \
		--css=style.css \
		--resource-path=. \
		src/movies.md


all:
	make website
	make movies