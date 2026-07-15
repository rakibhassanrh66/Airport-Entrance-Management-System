package airport.entrance.management;

import java.util.NoSuchElementException;
import java.util.Scanner;

/**
 * Console input helpers.
 *
 * <p>Everything here reads whole lines and parses them, rather than using
 * {@code Scanner.nextInt()}. Mixing {@code nextInt()} with {@code nextLine()}
 * leaves the rest of the line in the buffer, so the next {@code nextLine()}
 * returns "" instead of waiting for the user. Reading lines throughout avoids
 * that class of bug entirely.
 */
final class Console {

    private Console() {
    }

    /** Prompts and reads one trimmed line. Returns "" at end of input. */
    static String readLine(Scanner scanner, String prompt) {
        System.out.print(prompt);
        try {
            return scanner.nextLine().trim();
        } catch (NoSuchElementException eof) {
            // Piped or redirected input ran out. Return empty rather than crashing.
            System.out.println();
            return "";
        }
    }

    /** Prompts until the user types a whole number. Returns 0 at end of input. */
    static int readInt(Scanner scanner, String prompt) {
        while (true) {
            System.out.print(prompt);
            String line;
            try {
                line = scanner.nextLine().trim();
            } catch (NoSuchElementException eof) {
                System.out.println();
                return 0;
            }
            try {
                return Integer.parseInt(line);
            } catch (NumberFormatException notANumber) {
                System.out.println("  '" + line + "' is not a whole number. Try again.");
            }
        }
    }
}
