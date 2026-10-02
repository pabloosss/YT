class VisibleStream:
    """Suppress think blocks, including opening/closing tags split between chunks."""
    def __init__(self):
        self.pending = ""
        self.hidden = False

    def feed(self, text):
        self.pending += text
        output = []
        while self.pending:
            tag = "</think>" if self.hidden else "<think>"
            index = self.pending.lower().find(tag)
            if index >= 0:
                if not self.hidden:
                    output.append(self.pending[:index])
                self.pending = self.pending[index + len(tag):]
                self.hidden = not self.hidden
                continue
            hold = 0
            for length in range(1, min(len(tag), len(self.pending) + 1)):
                if self.pending.lower().endswith(tag[:length]):
                    hold = length
            safe = self.pending[:-hold] if hold else self.pending
            if not self.hidden:
                output.append(safe)
            self.pending = self.pending[-hold:] if hold else ""
            break
        return "".join(output)

    def finish(self):
        # An incomplete tag may still be the beginning of private content.
        self.pending = ""
        return ""
