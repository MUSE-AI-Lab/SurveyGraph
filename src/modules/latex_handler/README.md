`latex_text_builder` simply adds a prefix string and suffix string to the mainbody, the prefix string contains the preamble codes of latex, and the suffix string contains making reference code of latex.


`latex_figure_builder` will choose three chapters from mainbody.tex, these three chapters own the top three citation numbers in their content, which will be drawn into a structure figure. latex_figure_builder generate structure figure latex code and insert them into survey.tex

`latex_sheet_builder` will choose the section which contains the most cite number. And then generate sheet based on the section.