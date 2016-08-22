PREFIX=/usr/local
DEST=$(PREFIX)/bin


.PHONY: install install_scripts

# Use another level of indirection (rather than an order-only dependency for
# $(DEST)) to get around the chicken-and-the-egg problem
install: $(DEST) install_scripts $(DEST)/README.txt

$(DEST):
	install -d $@

install_scripts: $(DEST)/iptool

$(DEST)/iptool: iptool/__main__.py
	ln -s --force $$(pwd)/iptool/__main__.py $@
